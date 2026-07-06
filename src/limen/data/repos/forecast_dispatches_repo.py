"""Persistence + dedup for :class:`forecast_dispatches` (predictive alerts)."""

from __future__ import annotations

import json
from datetime import timedelta

from limen.core.logging import get_logger
from limen.data.db import acquire

log = get_logger(__name__)


async def dispatched_within(aoi_id: str, *, horizon_h: int, window: timedelta) -> bool:
    """``True`` when a forecast alert for (aoi, horizon) fired inside the window."""
    if window.total_seconds() <= 0:
        return False
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT 1 FROM forecast_dispatches
            WHERE aoi_id = $1 AND horizon_h = $2
              AND dispatched_at >= now() - $3::interval
            LIMIT 1
            """,
            aoi_id,
            horizon_h,
            window,
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
) -> None:
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO forecast_dispatches (
                aoi_id, horizon_h, max_level, max_score,
                cells_alerted, channels, summary
            ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
            """,
            aoi_id,
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
