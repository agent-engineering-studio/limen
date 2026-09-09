"""Lifespan + scheduler-registration integration tests."""

from __future__ import annotations

import pytest
from apscheduler import AsyncScheduler

from limen.agents.llm_factory.stub import StubLlmClientFactory
from limen.api.dependencies import AppDependencies
from limen.api.jobs.ids import (
    JOB_BRIEFING_ENRICHMENT,
    JOB_CACHE_CLEANUP,
    JOB_DRIFT_MONITOR,
    JOB_FORECAST_HISTORY,
    JOB_NIGHTLY,
)
from limen.api.jobs.registration import (
    JOB_HOURLY_MONITORING,
    JOB_HTML_REPORT,
    JOB_PARTITIONS,
    JOB_WEEKLY_IDROGEO,
    register_jobs,
)
from limen.config.settings import Settings
from limen.data.db import get_pool

pytestmark = pytest.mark.integration


async def test_register_jobs_schedules_enabled_jobs(reset_db: None, pg_pool: object) -> None:
    """The enabled periodic jobs land in the scheduler with the expected ids."""
    settings = Settings.model_validate({"scheduler": {"cache_cleanup": "apscheduler"}})
    deps = await AppDependencies.build(
        pool=get_pool(),
        settings=settings,
        llm_factory=StubLlmClientFactory(),
    )

    async with AsyncScheduler() as scheduler:
        registered = await register_jobs(scheduler, deps)
        # Re-running is idempotent (same ids replace, not duplicate).
        registered_again = await register_jobs(scheduler, deps)

    registered_set = set(registered)
    assert {
        JOB_HOURLY_MONITORING,
        JOB_WEEKLY_IDROGEO,
        JOB_HTML_REPORT,
        JOB_PARTITIONS,
        JOB_BRIEFING_ENRICHMENT,
        JOB_NIGHTLY,
    }.issubset(registered_set)
    # I tre schedule autonomi assorbiti dalla pipeline notturna (#78). Restano
    # dei job — girano dentro `limen-nightly` — ma non hanno più un tick loro,
    # ed è quello che questa asserzione protegge: reintrodurne uno li farebbe
    # girare due volte, e il retrain due volte è due volte Optuna.
    assert registered_set.isdisjoint({JOB_CACHE_CLEANUP, JOB_DRIFT_MONITOR, JOB_FORECAST_HISTORY})
    assert len(registered) == len(registered_set)  # no duplicate ids
    assert registered == registered_again  # idempotent re-registration


async def test_hourly_job_runs_for_each_aoi(reset_db: None, pg_pool: object) -> None:
    """Invoke ``run_hourly_monitoring`` directly — the scheduler is exercised
    elsewhere; here we verify the job's per-AOI semantics on an empty DB."""
    from limen.api.jobs.hourly_monitoring import run_hourly_monitoring

    settings = Settings.model_validate({})
    deps = await AppDependencies.build(
        pool=get_pool(),
        settings=settings,
        llm_factory=StubLlmClientFactory(),
    )
    # No AOIs seeded → job returns {} cleanly.
    result = await run_hourly_monitoring(deps)
    assert result == {}


async def test_register_jobs_skips_disabled(reset_db: None, pg_pool: object) -> None:
    """Disabling hourly + weekly removes exactly those two.

    Other default-enabled jobs (cache cleanup, HTML report, …) still register.
    """
    settings = Settings.model_validate(
        {
            "scheduler": {
                "cache_cleanup": "apscheduler",
                "enable_hourly_monitoring": False,
                "enable_weekly_idrogeo": False,
            }
        }
    )
    deps = await AppDependencies.build(
        pool=get_pool(),
        settings=settings,
        llm_factory=StubLlmClientFactory(),
    )
    async with AsyncScheduler() as scheduler:
        registered = await register_jobs(scheduler, deps)
    assert JOB_HOURLY_MONITORING not in registered
    assert JOB_WEEKLY_IDROGEO not in registered
    assert JOB_NIGHTLY in registered
    assert JOB_HTML_REPORT in registered  # report job still enabled by default


async def test_partitions_job_registers_under_pg_cron_backend(
    reset_db: None, pg_pool: object
) -> None:
    """Partition maintenance must not depend on the cache-cleanup backend.

    With ``SCHEDULER__CACHE_CLEANUP=pg_cron`` the cleanup is the database's
    job, and partition creation used to ride along inside it: after a week of
    uptime every hot-table write would land in the DEFAULT partition, which
    retention never drops. Dopo #78 la manutenzione sta nel notturno, ma la
    dipendenza da non ricreare è la stessa.
    """
    settings = Settings.model_validate({"scheduler": {"cache_cleanup": "pg_cron"}})
    deps = await AppDependencies.build(
        pool=get_pool(),
        settings=settings,
        llm_factory=StubLlmClientFactory(),
    )

    async with AsyncScheduler() as scheduler:
        registered = await register_jobs(scheduler, deps)

    assert JOB_CACHE_CLEANUP not in registered
    assert JOB_PARTITIONS in registered
    assert JOB_NIGHTLY in registered
