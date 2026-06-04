"""Persistence + dedup queries for :class:`alert_dispatches`."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from limen.core.logging import get_logger
from limen.data.db import acquire

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class AlertDispatchRow:
    """One persisted dispatch outcome."""

    cell_id: str
    aoi_id: str
    level: str
    score: float
    priority: float
    channels: dict[str, bool]
    summary: str | None
    dispatched_at: datetime | None = None


async def insert_many(rows: Iterable[AlertDispatchRow]) -> int:
    """Insert dispatch outcomes (one row per cell) in a single transaction."""
    rows_list = list(rows)
    if not rows_list:
        return 0
    async with acquire() as conn, conn.transaction():
        for r in rows_list:
            await conn.execute(
                """
                INSERT INTO alert_dispatches (
                    cell_id, aoi_id, level, score, priority, channels, summary
                ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
                """,
                r.cell_id,
                r.aoi_id,
                r.level,
                r.score,
                r.priority,
                json.dumps(r.channels, default=str),
                r.summary,
            )
    log.info("alert_dispatches.insert_many", count=len(rows_list))
    return len(rows_list)


async def cells_dispatched_within(
    cell_ids: Iterable[str],
    *,
    window: timedelta,
    now: datetime | None = None,
) -> set[str]:
    """Return the subset of ``cell_ids`` already alerted inside the window.

    ``now`` is exposed for tests that want a deterministic clock.
    """
    cells = list(cell_ids)
    if not cells:
        return set()
    if window.total_seconds() <= 0:
        return set()

    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT cell_id
            FROM alert_dispatches
            WHERE cell_id = ANY($1::text[])
              AND dispatched_at >= COALESCE($2, now()) - $3::interval
            """,
            cells,
            now,
            window,
        )
    return {str(r["cell_id"]) for r in rows}


async def count_dispatches() -> int:
    async with acquire() as conn:
        row = await conn.fetchrow("SELECT COUNT(*)::bigint AS n FROM alert_dispatches")
    return int(row["n"]) if row else 0


async def fetch_recent(
    *,
    aoi_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Convenience read used by tests and ad-hoc operator queries."""
    if aoi_id is None:
        sql = (
            "SELECT cell_id, aoi_id, level, score, priority, channels, "
            "summary, dispatched_at FROM alert_dispatches "
            "ORDER BY dispatched_at DESC LIMIT $1"
        )
        async with acquire() as conn:
            rows = await conn.fetch(sql, limit)
    else:
        sql = (
            "SELECT cell_id, aoi_id, level, score, priority, channels, "
            "summary, dispatched_at FROM alert_dispatches "
            "WHERE aoi_id = $1 ORDER BY dispatched_at DESC LIMIT $2"
        )
        async with acquire() as conn:
            rows = await conn.fetch(sql, aoi_id, limit)
    out: list[dict[str, Any]] = []
    for r in rows:
        channels = r["channels"]
        if isinstance(channels, str):
            channels = json.loads(channels)
        out.append(
            {
                "cell_id": r["cell_id"],
                "aoi_id": r["aoi_id"],
                "level": r["level"],
                "score": float(r["score"]),
                "priority": float(r["priority"]),
                "channels": channels or {},
                "summary": r["summary"],
                "dispatched_at": r["dispatched_at"],
            }
        )
    return out
