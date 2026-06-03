"""Cache-cleanup job — wraps :meth:`PostgresCache.cleanup_expired`.

Only registered when ``SCHEDULER__CACHE_CLEANUP=apscheduler``. On
local PostgreSQL with ``pg_cron`` available this job is skipped at
registration time — the migration in Prompt 1 schedules the cleanup
via pg_cron there.
"""

from __future__ import annotations

from limen.api.dependencies import AppDependencies
from limen.core.logging import get_logger

log = get_logger(__name__)


async def run_cache_cleanup_job(deps: AppDependencies) -> int:
    """Delete expired ``app_cache`` rows; returns the number removed."""
    try:
        removed = await deps.cache.cleanup_expired()  # type: ignore[attr-defined]
    except AttributeError:
        # Foreign DistributedCache impls aren't required to support cleanup.
        log.debug("job.cache_cleanup.not_supported")
        return 0
    except Exception as exc:
        log.error(
            "job.cache_cleanup.error",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return 0
    if removed:
        log.info("job.cache_cleanup.done", removed=removed)
    return int(removed)
