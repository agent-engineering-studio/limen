"""Lifespan + scheduler-registration integration tests."""

from __future__ import annotations

import pytest
from apscheduler import AsyncScheduler

from limen.agents.llm_factory.stub import StubLlmClientFactory
from limen.api.dependencies import AppDependencies
from limen.api.jobs.registration import (
    JOB_CACHE_CLEANUP,
    JOB_HOURLY_MONITORING,
    JOB_WEEKLY_IDROGEO,
    register_jobs,
)
from limen.config.settings import Settings
from limen.data.db import get_pool

pytestmark = pytest.mark.integration


async def test_register_jobs_schedules_three(reset_db: None, pg_pool: object) -> None:
    """All three periodic jobs land in the scheduler with the expected ids."""
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

    assert set(registered) == {
        JOB_HOURLY_MONITORING,
        JOB_WEEKLY_IDROGEO,
        JOB_CACHE_CLEANUP,
    }
    assert registered == registered_again


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
    """Disabling hourly + weekly only schedules cache cleanup."""
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
    assert registered == [JOB_CACHE_CLEANUP]
