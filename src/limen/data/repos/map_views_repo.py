"""Map-materialized-view refresh helper.

Wraps the ``refresh_mv_latest_risk()`` SQL function added by migration
``007_map_views.sql``. Callers (PersistResult executor + ad-hoc CLI)
invoke :func:`refresh_latest_risk` instead of issuing the
``REFRESH MATERIALIZED VIEW`` statement directly — keeps the fallback
logic (CONCURRENTLY → non-concurrent on first invocation) in one place.
"""

from __future__ import annotations

from limen.core.logging import get_logger
from limen.data.db import acquire

log = get_logger(__name__)


async def refresh_latest_risk() -> int:
    """Refresh ``mv_latest_risk``. Returns the SQL function's status code.

    Status semantics (mirror :func:`refresh_mv_latest_risk` in the SQL
    migration):

    * ``1`` → ``REFRESH MATERIALIZED VIEW CONCURRENTLY`` succeeded.
    * ``0`` → fell back to a blocking refresh (first run).
    * ``-1`` → refresh failed; details are in the Postgres log.
    """
    async with acquire() as conn:
        result = await conn.fetchval("SELECT refresh_mv_latest_risk()")
    code = int(result) if result is not None else -1
    log.info("map_views.refresh", code=code)
    return code
