"""In-process scheduler for periodic Limen jobs.

Used when ``SCHEDULER__CACHE_CLEANUP=apscheduler`` — typically on Neon, where
``pg_cron`` is unavailable. On local Docker Postgres with ``pg_cron``, this
module is simply not used.

We use APScheduler 4's async ``Scheduler`` (alpha at time of writing): the
job runs on the same event loop as the rest of the app.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from apscheduler import AsyncScheduler
from apscheduler.triggers.interval import IntervalTrigger

from limen.config.settings import (
    SchedulerBackend,
    SchedulerSettings,
    get_settings,
)
from limen.core.logging import get_logger
from limen.data.caching.postgres_cache import PostgresCache

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

log = get_logger(__name__)


async def _run_cache_cleanup() -> None:
    cache = PostgresCache()
    removed = await cache.cleanup_expired()
    if removed:
        log.info("scheduler.cache_cleanup", removed=removed)
    else:
        log.debug("scheduler.cache_cleanup", removed=0)


@asynccontextmanager
async def start_scheduler(
    settings: SchedulerSettings | None = None,
) -> AsyncIterator[AsyncScheduler | None]:
    """Start APScheduler with the Limen periodic jobs, if needed.

    Yields the scheduler (or ``None`` when pg_cron mode is selected). The
    scheduler is shut down cleanly on exit.
    """
    cfg = settings or get_settings().scheduler

    if cfg.cache_cleanup is SchedulerBackend.PG_CRON:
        log.info("scheduler.skip", reason="pg_cron mode selected")
        yield None
        return

    async with AsyncScheduler() as scheduler:
        await scheduler.add_schedule(
            _run_cache_cleanup,
            IntervalTrigger(seconds=cfg.cache_cleanup_interval_seconds),
            id="limen_app_cache_cleanup",
        )
        await scheduler.start_in_background()
        log.info(
            "scheduler.started",
            jobs=["limen_app_cache_cleanup"],
            interval_s=cfg.cache_cleanup_interval_seconds,
        )
        try:
            yield scheduler
        finally:
            await scheduler.stop()
            log.info("scheduler.stopped")


async def run_forever(settings: SchedulerSettings | None = None) -> None:
    """Run the scheduler until the process is interrupted. Useful for a worker."""
    async with start_scheduler(settings):
        await asyncio.Event().wait()
