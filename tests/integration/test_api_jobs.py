"""APScheduler job-runner smoke tests.

Phase-5 already verifies ``register_jobs`` registers the right ids; here
we invoke the job callables directly to exercise the per-job code path
end-to-end (DB read + workflow run / sync run / cache cleanup).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from limen.agents.llm_factory.stub import StubLlmClientFactory
from limen.api.dependencies import AppDependencies
from limen.api.jobs.cache_cleanup import run_cache_cleanup_job
from limen.api.jobs.hourly_monitoring import run_hourly_monitoring
from limen.api.jobs.weekly_idrogeo_sync import run_weekly_idrogeo_sync
from limen.cli.seed import run as run_seed
from limen.config.settings import Settings
from limen.data.db import acquire, get_pool
from limen.integrations._http import SharedHttpClient
from limen.integrations.openmeteo.client import ARCHIVE_URL, FORECAST_URL

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
async def _reset_http() -> None:
    await SharedHttpClient.aclose()
    yield
    await SharedHttpClient.aclose()


def _hourly_payload(hours: int = 24) -> dict[str, object]:
    base = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
    times = [(base + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(hours)]
    return {
        "latitude": 41.0,
        "longitude": 16.88,
        "hourly": {
            "time": times,
            "precipitation": [0.0] * hours,
            "soil_moisture_0_to_7cm": [0.25] * hours,
            "soil_moisture_7_to_28cm": [0.30] * hours,
            "snowfall": [0.0] * hours,
            "snow_depth": [0.0] * hours,
        },
    }


def _archive_payload() -> dict[str, object]:
    return {"daily": {"time": ["2026-05-31"], "precipitation_sum": [10.0]}}


async def _build_deps() -> AppDependencies:
    return await AppDependencies.build(
        pool=get_pool(),
        settings=Settings(),
        llm_factory=StubLlmClientFactory(),
    )


async def test_hourly_monitoring_runs_against_seeded_aois(
    reset_db: None,
    pg_pool: object,
) -> None:
    """Job iterates every seeded AOI and persists a RiskAssessment per cell."""
    await run_seed()
    # Pre-seed empty cell_static_factors so static factors load cleanly.
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cell_static_factors (cell_id)
            SELECT id FROM grid_cells
            ON CONFLICT (cell_id) DO NOTHING
            """
        )
        # Trim grids so the test doesn't score 60k cells per AOI.
        await conn.execute(
            """
            DELETE FROM grid_cells
            WHERE id NOT IN (SELECT id FROM grid_cells ORDER BY id LIMIT 6)
            """
        )

    deps = await _build_deps()
    with respx.mock(assert_all_called=False) as mock:
        mock.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=_hourly_payload()))
        mock.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=_archive_payload()))
        result = await run_hourly_monitoring(deps)

    # At least one AOI got at least one cell scored.
    assert sum(result.values()) > 0


async def test_weekly_idrogeo_sync_handles_unreachable_isp_gracefully(
    reset_db: None,
    pg_pool: object,
) -> None:
    """ISPRA WFS is mocked to 503 → the sync degrades, no exception escapes."""
    await run_seed()
    deps = await _build_deps()
    with respx.mock(assert_all_called=False) as mock:
        # Match any ISPRA WFS path
        mock.get(url__regex=r"https://idrogeo\.isprambiente\.it/.*").mock(
            return_value=httpx.Response(503)
        )
        result = await run_weekly_idrogeo_sync(deps)
    # Every AOI in the seeded set is iterated; degradation logs but
    # records an empty version anyway, so result is non-empty.
    assert isinstance(result, dict)


async def test_cache_cleanup_runs(reset_db: None, pg_pool: object) -> None:
    deps = await _build_deps()
    removed = await run_cache_cleanup_job(deps)
    assert removed >= 0
