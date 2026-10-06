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


async def summary_for_region(
    aoi_id: str, hazard: HazardType, *, top_k: int = TOP_CELLS
) -> AggregateAssessment | None:
    """Il riassunto di una regione per un pericolo, dallo stato attuale.

    Tutto da `latest_risk`, che è ciò che la mappa disegna, e niente dalle
    righe di uno sweep: lo sweep orario scrive nello storico solo le celle
    cambiate (#135), quindi un giro tranquillo non lascia righe — e un
    riassunto costruito da lì diceva «no rows» proprio quando la regione era
    ferma, o raccontava «384 celle, nessuna alta» di una regione che ne aveva
    migliaia (#155). Le celle non misurate restano fuori dai conteggi, come
    dall'attenzione: «non so» non è «nessuno».

    Ritorna ``None`` se la regione non ha ancora uno stato per quel pericolo.
    """
    async with acquire() as conn:
        head = await conn.fetchrow(
            """
            SELECT lr.horizon, lr.pipeline_version, lr.computed_at, lr.explanation
            FROM latest_risk lr
            JOIN grid_cells g ON g.id = lr.cell_id
            WHERE g.aoi_id = $1 AND lr.hazard_type = $2
            ORDER BY lr.computed_at DESC
            LIMIT 1
            """,
            aoi_id,
            hazard.value,
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
            aoi_id,
            hazard.value,
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
            aoi_id,
            hazard.value,
        )

    explanation = _coerce_json(head["explanation"])
    by_level = {str(r["class"]): int(r["n"]) for r in counts}
    top_cells = [record_from_row(r) for r in rows]
    valuation = explanation.get("valuation_time")
    return AggregateAssessment(
        aoi_id=aoi_id,
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
    )


__all__ = [
    "TOP_CELLS",
    "RiskAssessment",
    "insert",
    "latest_for_cell",
    "record_from_row",
    "summary_for_region",
]
