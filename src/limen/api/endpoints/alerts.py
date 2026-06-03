"""Recent alerts endpoint — high-or-above persisted assessments."""

from __future__ import annotations

from fastapi import APIRouter, Query

from limen.api.dependencies import DepsDep
from limen.api.schemas import AlertItem, AlertsResponse
from limen.data.db import acquire

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=AlertsResponse)
async def list_alerts(
    deps: DepsDep,  # noqa: ARG001 — DI presence
    threshold: str = Query("High", description="Minimum risk level to include"),
    since_hours: int = Query(72, ge=1, le=24 * 30),
    limit: int = Query(200, ge=1, le=2000),
) -> AlertsResponse:
    """Return the most recent persisted alerts above ``threshold``."""
    valid = {"None", "Low", "Moderate", "High", "VeryHigh"}
    if threshold not in valid:
        threshold = "High"

    # Levels at or above the requested threshold. Order is fixed so we
    # can short-circuit on string equality in the WHERE clause.
    order = ["None", "Low", "Moderate", "High", "VeryHigh"]
    levels_to_include = order[order.index(threshold) :]

    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ra.cell_id, g.aoi_id, ra.score, ra.class, ra.computed_at
            FROM risk_assessments ra
            JOIN grid_cells g ON g.id = ra.cell_id
            WHERE ra.class = ANY($1::text[])
              AND ra.computed_at >= now() - ($2::int * interval '1 hour')
            ORDER BY ra.computed_at DESC, ra.score DESC
            LIMIT $3
            """,
            levels_to_include,
            since_hours,
            limit,
        )

    items = [
        AlertItem(
            cell_id=str(r["cell_id"]),
            aoi_id=str(r["aoi_id"]),
            score=float(r["score"]),
            level=str(r["class"]),
            computed_at=r["computed_at"],
        )
        for r in rows
    ]
    return AlertsResponse(items=items)
