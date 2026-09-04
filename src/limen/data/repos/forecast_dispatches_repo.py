"""Persistence + dedup for :class:`forecast_dispatches` (predictive alerts)."""

from __future__ import annotations

import json
from datetime import timedelta

from limen.core.logging import get_logger
from limen.core.models.hazard import DEFAULT_HAZARD, HazardType
from limen.data.db import acquire

log = get_logger(__name__)


async def dispatched_within(
    aoi_id: str,
    *,
    horizon_h: int,
    window: timedelta,
    hazard: HazardType = DEFAULT_HAZARD,
) -> bool:
    """``True`` when a forecast alert for (aoi, hazard, horizon) fired inside
    the window."""
    if window.total_seconds() <= 0:
        return False
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT 1 FROM forecast_dispatches
            WHERE aoi_id = $1 AND horizon_h = $2 AND hazard_type = $4
              AND dispatched_at >= now() - $3::interval
            LIMIT 1
            """,
            aoi_id,
            horizon_h,
            window,
            hazard.value,
        )
    return row is not None


async def record_dispatch(
    *,
    aoi_id: str,
    horizon_h: int,
    max_level: str,
    max_score: float,
    cells_alerted: int,
    channels: dict[str, bool],
    summary: str | None,
    hazard: HazardType = DEFAULT_HAZARD,
) -> None:
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO forecast_dispatches (
                aoi_id, hazard_type, horizon_h, max_level, max_score,
                cells_alerted, channels, summary
            ) VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)
            """,
            aoi_id,
            hazard.value,
            horizon_h,
            max_level,
            max_score,
            cells_alerted,
            json.dumps(channels, default=str),
            summary,
        )
    log.info(
        "forecast_dispatches.recorded",
        aoi_id=aoi_id,
        horizon_h=horizon_h,
        cells=cells_alerted,
    )
