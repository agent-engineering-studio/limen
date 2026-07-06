"""Cache-cleanup job — wraps :meth:`PostgresCache.cleanup_expired`.

Only registered when ``SCHEDULER__CACHE_CLEANUP=apscheduler``. On
local PostgreSQL with ``pg_cron`` available this job is skipped at
registration time — the migration in Prompt 1 schedules the cleanup
via pg_cron there.
"""

from __future__ import annotations

from limen.api.dependencies import AppDependencies
from limen.core.logging import get_logger
from limen.data.db import acquire

log = get_logger(__name__)

# Per-tick cap: the job runs every few minutes, so retention deletes in
# small chronological batches (id is bigserial) instead of one huge sweep.
_RETENTION_BATCH = 50_000


async def _purge_old_model_runs(retention_days: int) -> int:
    if retention_days <= 0:
        return 0
    async with acquire() as conn:
        tag = await conn.execute(
            """
            DELETE FROM model_runs WHERE id IN (
                SELECT id FROM model_runs
                WHERE computed_at < now() - make_interval(days => $1)
                ORDER BY id
                LIMIT $2
            )
            """,
            retention_days,
            _RETENTION_BATCH,
        )
    return int(tag.split()[-1])


async def _purge_old_assessments(retention_days: int) -> int:
    """The hourly national sweep persists ~312k rows/tick (~15 GB/day):
    without retention the operational DB outgrows any host in weeks.
    mv_latest_risk keeps the map/report state; history beyond the window
    lives in backups, not in the hot table."""
    if retention_days <= 0:
        return 0
    async with acquire() as conn:
        tag = await conn.execute(
            """
            DELETE FROM risk_assessments WHERE id IN (
                SELECT id FROM risk_assessments
                WHERE computed_at < now() - make_interval(days => $1)
                ORDER BY id
                LIMIT $2
            )
            """,
            retention_days,
            _RETENTION_BATCH,
        )
    return int(tag.split()[-1])


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
    try:
        purged = await _purge_old_model_runs(deps.settings.scoring.model_runs_retention_days)
    except Exception as exc:
        log.error(
            "job.cache_cleanup.model_runs_error",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        purged = 0
    if removed or purged:
        log.info("job.cache_cleanup.done", removed=removed, model_runs_purged=purged)
    return int(removed)
