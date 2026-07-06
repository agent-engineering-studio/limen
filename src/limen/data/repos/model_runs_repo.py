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


async def insert_many(rows: Iterable[ModelRunRow]) -> int:
    items = list(rows)
    if not items:
        return 0
    async with acquire() as conn, conn.transaction():
        for it in items:
            await conn.execute(
                """
                INSERT INTO model_runs (
                    cell_id, valuation_time, aoi_id,
                    model_uri, model_version, role,
                    probability, risk_class, breakdown
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
                ON CONFLICT (cell_id, computed_at, role, model_uri) DO NOTHING
                """,
                it.cell_id,
                it.valuation_time,
                it.aoi_id,
                it.model_uri,
                it.model_version,
                it.role,
                it.probability,
                it.risk_class,
                json.dumps(it.breakdown, default=str),
            )
    log.info("model_runs.insert_many", count=len(items))
    return len(items)


async def recent_for_role(
    role: ModelRole,
    *,
    since: datetime,
    limit: int = 10_000,
    require_features: bool = False,
) -> list[ModelRunRow]:
    """Newest runs for a role. ``require_features`` keeps only rows whose
    breakdown carries the canonical feature vector (drift monitoring)."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT cell_id, valuation_time, aoi_id, model_uri, model_version,
                   role, probability, risk_class, breakdown
            FROM model_runs
            WHERE role = $1 AND computed_at >= $2
              AND (NOT $4 OR breakdown ? 'features')
            ORDER BY computed_at DESC
            LIMIT $3
            """,
            role,
            since,
            limit,
            require_features,
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
    )


__all__ = ["ModelRole", "ModelRunRow", "insert_many", "recent_for_role"]
