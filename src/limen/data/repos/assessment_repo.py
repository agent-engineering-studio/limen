"""Risk-assessment repository.

Le scritture dello sweep non passano di qui: le fa
:class:`~limen.agents.executors.persist_result.PersistResultExecutor` con una
COPY, e interporre un repo fra il COPY e la tabella significherebbe solo
riscrivere `copy_records_to_table` con un nome diverso.

Quello che vive qui è la lettura **per sweep** introdotta dal briefing
asincrono (#78): ricostruire il riassunto di una valutazione dalle righe che
ha scritto, e riattaccarci la narrativa quando arriva.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from limen.core.logging import get_logger
from limen.core.models.context import AggregateAssessment, CellRiskRecord
from limen.core.models.hazard import DEFAULT_HAZARD, HazardType
from limen.core.models.risk import RiskLevel, breakdown_from_factors
from limen.data.db import acquire

log = get_logger(__name__)

#: Quante celle di testa il riassunto ricostruito porta con sé. Cinque perché
#: è quante ne legge il prompt del briefing: ricostruirne di più significa
#: deserializzare breakdown che nessuno guarda.
TOP_CELLS = 5


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    cell_id: str
    horizon: str
    score: float
    class_: str
    factors: dict[str, Any]
    explanation: dict[str, Any]
    pipeline_version: str
    computed_at: datetime
    dataset_versions: list[int]
    hazard_type: HazardType = DEFAULT_HAZARD


async def insert(_: RiskAssessment) -> int:  # pragma: no cover - stub
    raise NotImplementedError("Risk assessment writes come in a later prompt")


async def latest_for_cell(  # pragma: no cover - stub
    _: str,
    /,
    *,
    horizon: str,
) -> RiskAssessment | None:
    raise NotImplementedError("Risk assessment reads come in a later prompt")


def _coerce_json(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    return dict(json.loads(value))


#: Le chiavi che una riga di frana può non avere perché è stata scritta prima
#: che il campo esistesse. Una cella storica merita di essere letta con dei
#: buchi neutri; un 500 su di lei non aiuta nessuno.
_NEUTRAL_LANDSLIDE_FACTORS: dict[str, Any] = {
    "s": 0.0,
    "m": 0.0,
    "e": 0.0,
    "f": 0.0,
    "h": 0.0,
    "static_terms": {
        "susc_ispra": 0.0,
        "iffi_density": 0.0,
        "slope": 0.0,
        "pai": 0.0,
        "litho_weight": 0.0,
    },
    "meteo_terms": {
        "caine_excess": 0.0,
        "caine_norm": 0.0,
        "api_factor": 0.5,
        "soil_factor": 0.5,
    },
}


def record_from_row(row: Any) -> CellRiskRecord:
    """Una riga di ``risk_assessments`` → un :class:`CellRiskRecord`.

    Vive qui e non nell'endpoint perché ha due lettori (#78): la risposta
    `/api/aoi/{id}/risk/latest` e la ricostruzione del riassunto per il
    briefing asincrono. Due decodifiche della stessa riga sarebbero divergite
    al primo campo aggiunto al breakdown, e la seconda l'avrebbe scoperto con
    un `ValidationError` dentro un job notturno.
    """
    hazard = HazardType(row["hazard_type"])
    factors = _coerce_json(row["factors"])
    if hazard is HazardType.LANDSLIDE:
        factors = {**_NEUTRAL_LANDSLIDE_FACTORS, **factors}
        meteo = dict(factors["meteo_terms"])
        # measured_overrides round-trips through JSON as a list; the DTO is a tuple.
        if "measured_overrides" in meteo:
            meteo["measured_overrides"] = tuple(meteo["measured_overrides"])
        factors["meteo_terms"] = meteo
    return CellRiskRecord(
        cell_id=str(row["cell_id"]),
        hazard_type=hazard,
        score=float(row["score"]),
        level=RiskLevel(str(row["class"])),
        breakdown=breakdown_from_factors(hazard, factors),
    )


async def summary_by_run(run_id: int, *, top_k: int = TOP_CELLS) -> AggregateAssessment | None:
    """Il riassunto di una regione per lo sweep ``run_id``, dallo stato attuale.

    Il briefing asincrono gira minuti dopo lo sweep, in un altro tick e
    potenzialmente in un altro processo: il `MonitoringContext` non esiste più.
    Dallo sweep si prendono i metadati — regione, pericolo, orizzonte,
    versione, il `briefing_it` già memorizzato — ma **conteggi e celle
    peggiori vengono da `latest_risk`** (#155). Lo sweep orario scrive solo le
    celle cambiate (#135), quindi le righe di un run sono una parte della
    regione: la spiegazione dell'incendio in Calabria parlava di «384 celle,
    nessuna alta» mentre la regione ne ha migliaia e Montegiordano era alta.
    Le celle non misurate restano fuori dai conteggi, come dall'attenzione:
    «non so» non è «nessuno».

    Ritorna ``None`` se lo sweep non ha lasciato righe (retention, o un run_id
    inventato).
    """
    async with acquire() as conn:
        head = await conn.fetchrow(
            """
            SELECT ra.hazard_type, ra.horizon, ra.pipeline_version,
                   ra.computed_at, ra.explanation, g.aoi_id
            FROM risk_assessments ra
            JOIN grid_cells g ON g.id = ra.cell_id
            WHERE ra.run_id = $1
            LIMIT 1
            """,
            run_id,
        )
        if head is None:
            return None
        rows = await conn.fetch(
            """
            SELECT lr.cell_id, lr.hazard_type, lr.score, lr.class, lr.factors
            FROM latest_risk lr
            JOIN grid_cells g ON g.id = lr.cell_id
            WHERE g.aoi_id = $1 AND lr.hazard_type = $2
              AND lr.score IS NOT NULL AND COALESCE(lr.measured, true)
            ORDER BY lr.score DESC, lr.cell_id
            LIMIT $3
            """,
            head["aoi_id"],
            head["hazard_type"],
            top_k,
        )
        counts = await conn.fetch(
            """
            SELECT lr.class, count(*) AS n
            FROM latest_risk lr
            JOIN grid_cells g ON g.id = lr.cell_id
            WHERE g.aoi_id = $1 AND lr.hazard_type = $2
              AND lr.score IS NOT NULL AND COALESCE(lr.measured, true)
            GROUP BY lr.class
            """,
            head["aoi_id"],
            head["hazard_type"],
        )

    hazard = HazardType(head["hazard_type"])
    explanation = _coerce_json(head["explanation"])
    by_level = {str(r["class"]): int(r["n"]) for r in counts}
    top_cells = [record_from_row(r) for r in rows]
    valuation = explanation.get("valuation_time")
    return AggregateAssessment(
        aoi_id=str(head["aoi_id"]),
        hazard_type=hazard,
        horizon=str(head["horizon"]),
        pipeline_version=str(head["pipeline_version"]),
        model_version=str(explanation.get("model_version") or head["pipeline_version"]),
        valuation_time=(
            datetime.fromisoformat(str(valuation)) if valuation else head["computed_at"]
        ),
        n_cells=sum(by_level.values()),
        cells_high_or_above=by_level.get(RiskLevel.High.value, 0)
        + by_level.get(RiskLevel.VeryHigh.value, 0),
        cells_by_level=by_level,
        top_cells=top_cells,
        briefing_it=str(explanation["briefing_it"]) if explanation.get("briefing_it") else None,
    )


async def attach_narrative(
    run_id: int,
    *,
    briefing_it: str,
    analysis: dict[str, Any] | None,
) -> int:
    """Aggiungi narrativa e analisi alle righe di uno sweep. Ritorna le righe toccate.

    `explanation || jsonb_build_object(...)`: una fusione, non una
    sostituzione, così `model_version` e `valuation_time` restano quelli
    scritti dallo sweep. E soltanto `explanation`: `score`, `class` e `factors`
    non compaiono nella SET, che è l'invariante "l'LLM non tocca i numeri"
    scritta in SQL invece che sperata.
    """
    payload = json.dumps(analysis, default=str) if analysis is not None else None
    async with acquire() as conn, conn.transaction():
        status = await conn.execute(
            """
            UPDATE risk_assessments
            SET explanation = explanation || jsonb_build_object(
                    'briefing_it', $2::text,
                    'analysis', $3::jsonb
                )
            WHERE run_id = $1
            """,
            run_id,
            briefing_it,
            payload,
        )
        # Lo stesso testo va su `latest_risk`, che dalla #125 è ciò che la
        # mappa e le API leggono: senza questa riga il briefing resterebbe
        # nello storico e non lo vedrebbe nessuno. Anche qui solo
        # `explanation`, e per le sole celle di quello sweep — l'invariante
        # "l'LLM non tocca i numeri" vale identica sulle due tabelle.
        # Per `run_id` e non unendo a `risk_assessments` (#135): con lo
        # storico rado quell'unione troverebbe le sole celle cambiate, e il
        # briefing arriverebbe a una manciata di celle invece che all'area
        # intera. `latest_risk.run_id` dice quale sweep ha prodotto lo stato,
        # che è esattamente l'insieme a cui la narrativa si riferisce.
        await conn.execute(
            """
            UPDATE latest_risk
            SET explanation = explanation || jsonb_build_object(
                    'briefing_it', $2::text,
                    'analysis', $3::jsonb
                )
            WHERE run_id = $1
            """,
            run_id,
            briefing_it,
            payload,
        )
    updated = int(status.split()[-1]) if status else 0
    log.info("assessment.narrative_attached", run_id=run_id, rows=updated)
    return updated


__all__ = [
    "TOP_CELLS",
    "RiskAssessment",
    "attach_narrative",
    "insert",
    "latest_for_cell",
    "record_from_row",
    "summary_by_run",
]
