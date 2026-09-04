"""Daily-partition maintenance for the hot tables.

``risk_assessments`` and ``model_runs`` are RANGE-partitioned on
``computed_at``, one partition per UTC day. Two things have to happen for
that to keep working: the partitions for the coming days must exist before a
sweep tries to write into them, and the ones past the retention window must
be dropped. Both are single SQL calls into functions created by the
migration -- the DDL is assembled there, not here.
"""

from __future__ import annotations

from typing import Final

from limen.core.logging import get_logger
from limen.data.db import acquire

log = get_logger(__name__)

PARTITIONED_TABLES: Final[tuple[str, ...]] = ("risk_assessments", "model_runs")


async def ensure(*, days_ahead: int = 7) -> dict[str, int]:
    """Create the missing partitions for every hot table. Returns per-table counts."""
    created: dict[str, int] = {}
    async with acquire() as conn:
        for table in PARTITIONED_TABLES:
            n = await conn.fetchval("SELECT ensure_partitions($1, $2)", table, days_ahead)
            created[table] = int(n or 0)
    if any(created.values()):
        log.info("partitions.ensured", created=created, days_ahead=days_ahead)
    return created


async def drop_expired(table: str, retention_days: int) -> int:
    """Drop the dated partitions older than the retention window."""
    async with acquire() as conn:
        n = await conn.fetchval("SELECT drop_expired_partitions($1, $2)", table, retention_days)
    return int(n or 0)


async def default_partition_rows(table: str) -> int:
    """Rows sitting in the DEFAULT partition.

    Non-zero means a write landed on a day with no partition, so
    :func:`ensure` did not run in time. The rows are safe but they defeat
    retention, which only drops dated partitions.
    """
    if table not in PARTITIONED_TABLES:
        raise ValueError(f"unknown partitioned table {table!r}")
    async with acquire() as conn:
        # A relation name cannot be a bind parameter. `table` is checked
        # against the module constant above, so the interpolation is closed.
        n = await conn.fetchval(f"SELECT count(*) FROM ONLY {table}_default")
    return int(n or 0)


async def warn_on_default_rows() -> None:
    """Log a warning for every hot table whose DEFAULT partition is not empty."""
    for table in PARTITIONED_TABLES:
        rows = await default_partition_rows(table)
        if rows:
            log.warning("partitions.default_not_empty", table=table, rows=rows)


__all__ = [
    "PARTITIONED_TABLES",
    "default_partition_rows",
    "drop_expired",
    "ensure",
    "warn_on_default_rows",
]
