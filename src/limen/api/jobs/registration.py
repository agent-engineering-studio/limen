"""Register Limen's periodic jobs on an :class:`AsyncScheduler`.

Idempotent: each job has a stable ``id`` so re-running ``register_jobs``
(e.g. after a lifespan restart in tests) replaces the previous schedule
rather than stacking.
"""

from __future__ import annotations

from apscheduler import AsyncScheduler, ConflictPolicy
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from limen.api.dependencies import AppDependencies
from limen.api.jobs.cache_cleanup import run_cache_cleanup_job
from limen.api.jobs.hourly_monitoring import run_hourly_monitoring
from limen.api.jobs.weekly_idrogeo_sync import run_weekly_idrogeo_sync
from limen.config.settings import SchedulerBackend
from limen.core.logging import get_logger

log = get_logger(__name__)

JOB_HOURLY_MONITORING = "limen-hourly-monitoring"
JOB_WEEKLY_IDROGEO = "limen-weekly-idrogeo"
JOB_CACHE_CLEANUP = "limen-cache-cleanup"


async def register_jobs(scheduler: AsyncScheduler, deps: AppDependencies) -> list[str]:
    """Schedule every Limen periodic job. Returns the list of job ids registered."""
    cfg = deps.settings.scheduler
    registered: list[str] = []

    if cfg.enable_hourly_monitoring:
        await scheduler.add_schedule(
            run_hourly_monitoring,
            args=(deps,),
            trigger=IntervalTrigger(minutes=cfg.hourly_monitoring_minutes),
            id=JOB_HOURLY_MONITORING,
            conflict_policy=ConflictPolicy.replace,
        )
        registered.append(JOB_HOURLY_MONITORING)
        log.info(
            "scheduler.registered",
            job=JOB_HOURLY_MONITORING,
            interval_minutes=cfg.hourly_monitoring_minutes,
        )

    if cfg.enable_weekly_idrogeo:
        await scheduler.add_schedule(
            run_weekly_idrogeo_sync,
            args=(deps,),
            trigger=CronTrigger(day_of_week="mon", hour=3, minute=15),
            id=JOB_WEEKLY_IDROGEO,
            conflict_policy=ConflictPolicy.replace,
        )
        registered.append(JOB_WEEKLY_IDROGEO)
        log.info(
            "scheduler.registered",
            job=JOB_WEEKLY_IDROGEO,
            cron="mon 03:15",
        )

    if cfg.cache_cleanup is SchedulerBackend.APSCHEDULER:
        await scheduler.add_schedule(
            run_cache_cleanup_job,
            args=(deps,),
            trigger=IntervalTrigger(seconds=cfg.cache_cleanup_interval_seconds),
            id=JOB_CACHE_CLEANUP,
            conflict_policy=ConflictPolicy.replace,
        )
        registered.append(JOB_CACHE_CLEANUP)
        log.info(
            "scheduler.registered",
            job=JOB_CACHE_CLEANUP,
            interval_seconds=cfg.cache_cleanup_interval_seconds,
        )

    return registered
