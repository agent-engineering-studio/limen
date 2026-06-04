"""Rolling-window partition management for ``sensor_observations``.

The migration seeds ±6 months on first apply. After that, a small
APScheduler job calls :func:`ensure_partition_window` once a month to
keep the same window in sync — without it, an observation that lands
on the first day of a new month would have no partition to go to.
"""

from __future__ import annotations

from datetime import date

import asyncpg
import structlog

from limen.core.logging import get_logger

_log: structlog.stdlib.BoundLogger = get_logger(__name__)


def _first_of_month(d: date) -> date:
    return d.replace(day=1)


def _month_offset(d: date, months: int) -> date:
    total = d.year * 12 + (d.month - 1) + months
    year, month = divmod(total, 12)
    return date(year, month + 1, 1)


async def ensure_partition_window(
    conn: asyncpg.Connection,
    *,
    reference: date,
    window_months: int,
) -> list[str]:
    """Ensure partitions exist for ``[reference - window, reference + window]``.

    Returns the list of partition names touched. Idempotent — the
    underlying SQL helper uses ``CREATE TABLE IF NOT EXISTS``.
    """
    if window_months < 1:
        raise ValueError("window_months must be >= 1")
    anchor = _first_of_month(reference)
    touched: list[str] = []
    for offset in range(-window_months, window_months + 1):
        month_start = _month_offset(anchor, offset)
        name = await conn.fetchval(
            "SELECT ensure_sensor_partition_for_month($1::date)", month_start
        )
        touched.append(str(name))
    _log.debug(
        "iot.partitions.ensured",
        reference=str(reference),
        window_months=window_months,
        count=len(touched),
    )
    return touched


__all__ = ["ensure_partition_window"]
