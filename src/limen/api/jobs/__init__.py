"""APScheduler jobs run in-process alongside the FastAPI app.

Public surface:

* :func:`register_jobs` — registers every Limen periodic job on a
  running :class:`AsyncScheduler`. Called from the FastAPI lifespan.

Job design rules:

* Each job is a small async coroutine taking the
  :class:`AppDependencies` container — no globals.
* ``max_running_jobs=1`` per job so a slow run can't overlap.
* Misfire grace ~ half the trigger interval (APScheduler 4 default).
* Every job catches exceptions and logs them so a single failure
  doesn't take the scheduler down.
"""

from limen.api.jobs.cache_cleanup import run_cache_cleanup_job
from limen.api.jobs.hourly_monitoring import run_hourly_monitoring
from limen.api.jobs.registration import register_jobs
from limen.api.jobs.weekly_idrogeo_sync import run_weekly_idrogeo_sync

__all__ = [
    "register_jobs",
    "run_cache_cleanup_job",
    "run_hourly_monitoring",
    "run_weekly_idrogeo_sync",
]
