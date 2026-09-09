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
    """Writes one ``risk_assessments`` row per scored cell, in una COPY."""

    def __init__(self, *, horizon: str = "24h", hazard: HazardType = DEFAULT_HAZARD) -> None:
        super().__init__(name="PersistResult")
        self._horizon = horizon
        self._hazard = hazard

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
            await conn.copy_records_to_table(
                "risk_assessments", records=records, columns=list(_COPY_COLUMNS)
            )

        # Best-effort refresh of the map's materialized view so the
        # frontend sees the new scores immediately. Failure here MUST
        # NOT block the workflow — the matview can also be refreshed by
        # a periodic job or by the operator.
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
            cells_persisted=len(records),
            run_id=run_id,
        )
        return ctx.with_update(assessment_id=run_id)
