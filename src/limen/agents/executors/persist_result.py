"""Persist the assessment to ``risk_assessments``.

Writes **one row per evaluated cell** (Phase 1 schema). The
pipeline_version + dataset_versions array link the persisted score back to the
YAML config that produced it. dataset_versions is left empty in V1 because the
per-cell scoring doesn't yet pin to specific ingest snapshots.

**Una COPY, non un INSERT per cella** (#76). Il ciclo `fetchrow` costava un
round-trip per cella: misurato 13,2 s per le 10.353 celle della Basilicata,
contro 0,88 s dello scoring vero. Su scala nazionale erano ~312.000
round-trip per sweep.

Due dettagli imparati provandolo su Postgres vero, perché la issue chiedeva
di verificarli:

* il COPY binario di asyncpg accetta **`jsonb` come `str`** e l'enum
  `hazard_type` come `str`. Nessuna tabella temporanea, nessun
  `INSERT ... SELECT unnest(...)`: `copy_records_to_table` basta.
* ``computed_at`` va passato esplicitamente — con COPY non c'è un `now()`
  lato SQL. È un miglioramento e non una concessione: **un solo istante per
  tutto lo sweep dell'AOI**, quindi le righe di una regione condividono il
  timestamp. Prima ogni cella aveva il proprio `now()`, che rendeva
  `mv_latest_risk` una scelta fra 10.000 istanti diversi e la chiave di
  partizione non allineata all'interno di uno stesso sweep.

L'identificatore restituito nel contesto non è più il `RETURNING id`
dell'ultima riga — che nominava una cella arbitraria — ma un id di **sweep**
da `assessment_run_id_seq`: `WHERE run_id = X` dà esattamente le righe di una
valutazione.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from limen.agents.workflow_runtime.executor import Executor, handler
from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext
from limen.core.models.hazard import DEFAULT_HAZARD, HazardType
from limen.data.db import acquire

log = get_logger(__name__)

#: Colonne della COPY, nell'ordine dei record. `id` è generated-by-default,
#: quindi si omette e Postgres la assegna anche in COPY.
_COPY_COLUMNS = (
    "cell_id",
    "computed_at",
    "hazard_type",
    "horizon",
    "score",
    "class",
    "factors",
    "explanation",
    "pipeline_version",
    "dataset_versions",
    "run_id",
)


class PersistResultExecutor(Executor):
    """Scrive lo stato corrente di ogni cella, e la storia solo di chi cambia."""

    def __init__(
        self,
        *,
        horizon: str = "24h",
        hazard: HazardType = DEFAULT_HAZARD,
        history_min_delta: float | None = None,
        history_heartbeat_hours: int | None = None,
    ) -> None:
        super().__init__(name="PersistResult")
        self._horizon = horizon
        self._hazard = hazard
        # I due parametri sono iniettabili per i test, che devono poter
        # provare «scrivi sempre» e «non scrivere mai» senza variabili
        # d'ambiente; in esercizio vengono dalle impostazioni.
        scoring = get_settings().scoring
        self._history_min_delta = (
            scoring.history_min_delta if history_min_delta is None else history_min_delta
        )
        self._history_heartbeat_hours = (
            scoring.history_heartbeat_hours
            if history_heartbeat_hours is None
            else history_heartbeat_hours
        )

    @handler
    async def run(self, ctx: MonitoringContext) -> MonitoringContext:
        assessment = ctx.assessment
        if assessment is None:
            log.warning("executor.persist_result.skip", reason="no assessment in ctx")
            return ctx
        if not ctx.cell_results:
            log.info("executor.persist_result.empty", aoi_id=ctx.aoi_id)
            return ctx

        # The AOI-level briefing is folded into every cell's explanation
        # blob so an analyst can answer "why?" from a single row.
        analysis_payload = (
            assessment.analysis.model_dump() if assessment.analysis is not None else None
        )
        # Serializzato una volta: è identico su tutte le celle, e rifarlo per
        # cella era il secondo costo del vecchio ciclo dopo i round-trip.
        explanation = json.dumps(
            {
                "model_version": assessment.model_version,
                "valuation_time": assessment.valuation_time.isoformat(),
                "analysis": analysis_payload,
                "briefing_it": assessment.briefing_it,
            },
            default=str,
        )
        computed_at = datetime.now(UTC)

        async with acquire() as conn, conn.transaction():
            run_id = int(await conn.fetchval("SELECT nextval('assessment_run_id_seq')"))
            records: list[tuple[Any, ...]] = [
                (
                    cell.cell_id,
                    computed_at,
                    self._hazard.value,
                    self._horizon,
                    cell.score,
                    cell.level.value,
                    # Il payload lo decide il breakdown, non questo executor:
                    # la forma segue il pericolo che l'ha prodotta, e per le
                    # frane è identica a quella scritta prima che la
                    # proiezione esistesse.
                    json.dumps(cell.breakdown.factors_payload(), default=str),
                    explanation,
                    assessment.pipeline_version,
                    [],
                    run_id,
                )
                for cell in ctx.cell_results
            ]
            # Le righe dello sweep passano da una tabella temporanea, non
            # direttamente nello storico (#135). Serve a decidere *prima* di
            # scrivere quali celle meritano una riga: il confronto è con
            # `latest_risk`, che a questo punto contiene ancora lo stato
            # precedente.
            await conn.execute(
                """
                CREATE TEMP TABLE sweep_rows (
                    cell_id          text,
                    computed_at      timestamptz,
                    hazard_type      hazard_type,
                    horizon          text,
                    score            double precision,
                    class            text,
                    factors          jsonb,
                    explanation      jsonb,
                    pipeline_version text,
                    dataset_versions bigint[],
                    run_id           bigint
                ) ON COMMIT DROP
                """
            )
            await conn.copy_records_to_table(
                "sweep_rows", records=records, columns=list(_COPY_COLUMNS)
            )

            # Cosa è una notizia: una cella mai vista, un cambio di classe,
            # uno scostamento di punteggio oltre la soglia, o il battito
            # scaduto. Tutto il resto è la stessa cosa dell'ora prima, e
            # riscriverla ventiquattro volte al giorno è ciò che ha riempito
            # il disco.
            #
            # `history_at` e non `computed_at`: il secondo si aggiorna a ogni
            # giro anche quando non scriviamo, quindi il battito misurato su
            # quello non scadrebbe mai.
            await conn.execute(
                """
                CREATE TEMP TABLE sweep_keep ON COMMIT DROP AS
                SELECT s.*,
                       lr.history_at AS prev_history_at,
                       (
                            lr.cell_id IS NULL
                         OR lr.class IS DISTINCT FROM s.class
                         OR abs(coalesce(lr.score, -1.0) - s.score) >= $1
                         OR lr.history_at IS NULL
                         OR s.computed_at - lr.history_at
                              >= make_interval(hours => $2)
                       ) AS keep
                FROM sweep_rows s
                LEFT JOIN latest_risk lr
                       ON lr.cell_id = s.cell_id
                      AND lr.hazard_type = s.hazard_type
                """,
                float(self._history_min_delta),
                int(self._history_heartbeat_hours),
            )

            scritte = await conn.fetchval("SELECT count(*) FROM sweep_keep WHERE keep")
            await conn.execute(
                f"""
                INSERT INTO risk_assessments ({", ".join(_COPY_COLUMNS)})
                SELECT {", ".join(_COPY_COLUMNS)} FROM sweep_keep WHERE keep
                """
            )

            # Lo stato corrente invece è **sempre** completo: è la mappa.
            # `history_at` avanza solo per le celle che hanno lasciato una
            # riga, così il battito successivo si misura da lì.
            #
            # La guardia sul `computed_at` serve a un replay: una riga più
            # vecchia non deve sovrascrivere una più recente solo perché è
            # arrivata dopo.
            await conn.execute(
                """
                INSERT INTO latest_risk (
                    cell_id, hazard_type, score, class, horizon,
                    pipeline_version, computed_at, factors, explanation,
                    history_at, run_id
                )
                SELECT k.cell_id, k.hazard_type, k.score, k.class, k.horizon,
                       k.pipeline_version, k.computed_at, k.factors, k.explanation,
                       CASE WHEN k.keep THEN k.computed_at ELSE k.prev_history_at END,
                       k.run_id
                FROM sweep_keep k
                -- Le righe previsionali (`horizon` '+24h') le scrive
                -- `forecast_history` per il grafico dell'andamento, e non
                -- sono lo stato corrente di niente.
                WHERE k.horizon NOT LIKE '+%'
                ON CONFLICT (cell_id, hazard_type) DO UPDATE
                SET score            = EXCLUDED.score,
                    class            = EXCLUDED.class,
                    horizon          = EXCLUDED.horizon,
                    pipeline_version = EXCLUDED.pipeline_version,
                    computed_at      = EXCLUDED.computed_at,
                    factors          = EXCLUDED.factors,
                    explanation      = EXCLUDED.explanation,
                    history_at       = EXCLUDED.history_at,
                    run_id           = EXCLUDED.run_id
                WHERE latest_risk.computed_at <= EXCLUDED.computed_at
                """
            )

        # La mappa è già aggiornata: `mv_latest_risk` è una vista su
        # `latest_risk`, appena scritta qui sopra. Questa chiamata aggiorna il
        # rollup per comune, che resta un aggregato materializzato. Best
        # effort: un rollup fallito non deve fermare lo sweep.
        try:
            from limen.data.repos.map_views_repo import refresh_latest_risk

            await refresh_latest_risk()
        except Exception as exc:
            log.warning(
                "executor.persist_result.refresh_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )

        log.info(
            "executor.persist_result",
            aoi_id=ctx.aoi_id,
            # Due numeri e non uno: lo stato corrente è sempre completo, lo
            # storico no. Il loro rapporto è la misura del #135 — se tornano
            # a coincidere, la scrittura selettiva ha smesso di funzionare.
            cells_current=len(records),
            cells_history=int(scritte or 0),
            run_id=run_id,
        )
        return ctx.with_update(assessment_id=run_id)
