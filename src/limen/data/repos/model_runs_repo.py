"""Per-cell challenger predictions captured in shadow mode (V2).

The champion's scores still land in :sql:`risk_assessments`; this
table is the parallel record of what the challenger would have said.
Live evaluation + drift monitoring read here.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from limen.core.logging import get_logger
from limen.core.models.hazard import DEFAULT_HAZARD, HazardType
from limen.data.db import acquire

log = get_logger(__name__)


ModelRole = Literal["champion", "challenger"]


@dataclass(frozen=True, slots=True)
class ModelRunRow:
    cell_id: str
    valuation_time: datetime
    aoi_id: str | None
    model_uri: str
    model_version: str
    role: ModelRole
    probability: float
    risk_class: str
    breakdown: dict[str, Any]
    hazard_type: HazardType = DEFAULT_HAZARD


#: Colonne della staging, nell'ordine dei record.
_STAGING_COLUMNS = (
    "cell_id",
    "valuation_time",
    "aoi_id",
    "hazard_type",
    "model_uri",
    "model_version",
    "role",
    "probability",
    "risk_class",
    "breakdown",
)


async def insert_many(rows: Iterable[ModelRunRow]) -> int:
    """Scrive le righe dello shadow in una COPY (#76).

    **COPY in una temporanea, poi INSERT … SELECT … ON CONFLICT**, e non una
    COPY diretta: il vincolo `UNIQUE (cell_id, hazard_type, computed_at, role,
    model_uri)` esiste perché due sweep sovrapposti non devono duplicare le
    righe, e la COPY non sa fare `ON CONFLICT`. La issue suggeriva di
    rinunciare al vincolo contando sul worker unico che arriverà con #77:
    sarebbe stato fidarsi di un passo non ancora fatto, e il costo di tenerlo
    è una tabella temporanea che vive dentro la transazione.

    Resta comunque un paio di round-trip invece di uno per riga.
    """
    items = list(rows)
    if not items:
        return 0
    records = [
        (
            it.cell_id,
            it.valuation_time,
            it.aoi_id,
            it.hazard_type.value,
            it.model_uri,
            it.model_version,
            it.role,
            it.probability,
            it.risk_class,
            json.dumps(it.breakdown, default=str),
        )
        for it in items
    ]
    async with acquire() as conn, conn.transaction():
        # ON COMMIT DROP: la temporanea vive quanto la transazione, quindi
        # due sweep concorrenti non se la contendono e non resta niente da
        # ripulire se qualcosa esplode a metà.
        await conn.execute(
            "CREATE TEMP TABLE _model_runs_staging "
            "(LIKE model_runs INCLUDING DEFAULTS) ON COMMIT DROP"
        )
        await conn.copy_records_to_table(
            "_model_runs_staging", records=records, columns=list(_STAGING_COLUMNS)
        )
        await conn.execute(
            """
            INSERT INTO model_runs (
                cell_id, valuation_time, aoi_id, hazard_type,
                model_uri, model_version, role,
                probability, risk_class, breakdown
            )
            SELECT cell_id, valuation_time, aoi_id, hazard_type,
                   model_uri, model_version, role,
                   probability, risk_class, breakdown
            FROM _model_runs_staging
            ON CONFLICT (cell_id, hazard_type, computed_at, role, model_uri)
            DO NOTHING
            """
        )
    log.info("model_runs.insert_many", count=len(items))
    return len(items)


async def recent_for_role(
    role: ModelRole,
    *,
    since: datetime,
    limit: int = 10_000,
    require_features: bool = False,
    hazard: HazardType = DEFAULT_HAZARD,
) -> list[ModelRunRow]:
    """Newest runs for a role. ``require_features`` keeps only rows whose
    breakdown carries the canonical feature vector (drift monitoring)."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT cell_id, valuation_time, aoi_id, hazard_type, model_uri,
                   model_version, role, probability, risk_class, breakdown
            FROM model_runs
            WHERE role = $1 AND computed_at >= $2
              AND hazard_type = $5
              AND (NOT $4 OR breakdown ? 'features')
            ORDER BY computed_at DESC
            LIMIT $3
            """,
            role,
            since,
            limit,
            require_features,
            hazard.value,
        )
    return [_to_row(r) for r in rows]


def _to_row(r: Any) -> ModelRunRow:
    breakdown = r["breakdown"]
    if isinstance(breakdown, str):
        breakdown = json.loads(breakdown)
    return ModelRunRow(
        cell_id=r["cell_id"],
        valuation_time=r["valuation_time"],
        aoi_id=r["aoi_id"],
        model_uri=r["model_uri"],
        model_version=r["model_version"],
        role=r["role"],
        probability=float(r["probability"]),
        risk_class=r["risk_class"],
        breakdown=breakdown or {},
        hazard_type=HazardType(r["hazard_type"]),
    )


__all__ = ["ModelRole", "ModelRunRow", "insert_many", "recent_for_role"]
