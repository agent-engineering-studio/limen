"""Smoke tests for every ``limen`` CLI subcommand runner.

Each runner is a thin orchestration around the same primitives already
exercised by lower-level tests; here we just confirm the entry point
itself opens the pool, runs its work, and closes cleanly.

Coverage motive: bumps the otherwise-untouched ``src/limen/cli/*``
modules from 0% to 80%+ via a single end-to-end happy path.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from limen.agents.llm_factory.stub import StubLlmClientFactory
from limen.cli.backtest import run as run_backtest
from limen.cli.bootstrap_static import run as run_bootstrap_static
from limen.cli.calibrate import run as run_calibrate
from limen.cli.migrate import run as run_migrate
from limen.cli.monitor_once import run as run_monitor_once
from limen.cli.seed import run as run_seed
from limen.integrations._http import SharedHttpClient
from limen.integrations.openmeteo.client import ARCHIVE_URL, FORECAST_URL

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
async def _reset_http() -> AsyncIterator[None]:
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


async def test_migrate_runs(reset_db: None, pg_pool: object) -> None:
    """`limen migrate` is idempotent on an already-migrated DB."""
    rc = await run_migrate()
    assert rc == 0


async def test_seed_runs(reset_db: None, pg_pool: object) -> None:
    rc = await run_seed()
    assert rc == 0


async def test_bootstrap_static_runs(reset_db: None, pg_pool: object) -> None:
    """Seed then bootstrap-static — exercises the orchestrator end-to-end."""
    await run_seed()
    rc = await run_bootstrap_static()
    assert rc == 0


async def test_calibrate_runs(reset_db: None, pg_pool: object, tmp_path: Path) -> None:
    """Calibrate writes its markdown report under ./reports/."""
    # Reports are written relative to cwd; use a tmpdir so the test
    # leaves no artefacts behind.
    cwd_before = Path.cwd()
    os.chdir(tmp_path)
    try:
        await run_seed()
        await run_bootstrap_static()
        rc = await run_calibrate()
    finally:
        os.chdir(cwd_before)
    assert rc == 0
    assert (tmp_path / "reports").exists()


async def test_monitor_once_runs(reset_db: None, pg_pool: object) -> None:
    """monitor-once: seed → bootstrap → monitor against mocked Open-Meteo.

    Forces the LLM factory to the deterministic Stub via env-injected
    settings so we don't depend on any provider's key.
    """
    await run_seed()
    await run_bootstrap_static()

    # Patch the resolver path: monkeypatch the import-time function so
    # the CLI picks up our stub factory.
    import limen.cli.monitor_once as monitor_mod

    real_resolve = monitor_mod.resolve_llm_factory

    def _stub_resolve(_settings):  # type: ignore[no-untyped-def]
        return StubLlmClientFactory()

    monitor_mod.resolve_llm_factory = _stub_resolve  # type: ignore[assignment]
    os.environ["LIMEN_MONITOR_AOI"] = "it-puglia"
    os.environ["LIMEN_MONITOR_CELL_LIMIT"] = "5"

    try:
        with respx.mock(assert_all_called=False) as mock:
            mock.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=_hourly_payload()))
            mock.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=_archive_payload()))
            rc = await run_monitor_once()
    finally:
        monitor_mod.resolve_llm_factory = real_resolve  # type: ignore[assignment]
        os.environ.pop("LIMEN_MONITOR_AOI", None)
        os.environ.pop("LIMEN_MONITOR_CELL_LIMIT", None)
    assert rc == 0


async def test_backtest_runs(
    reset_db: None,
    pg_pool: object,
    tmp_path: Path,
) -> None:
    """backtest: seed + bootstrap + a narrow window → §2.5 report file.

    The window is a single hour so the test stays fast even with hourly
    bundle assembly.
    """
    await run_seed()
    await run_bootstrap_static()
    os.environ["LIMEN_BACKTEST_AOI"] = "it-puglia"
    os.environ["LIMEN_BACKTEST_START"] = datetime(2026, 5, 1, 12, tzinfo=UTC).isoformat()
    os.environ["LIMEN_BACKTEST_END"] = datetime(2026, 5, 1, 13, tzinfo=UTC).isoformat()

    cwd_before = Path.cwd()
    os.chdir(tmp_path)
    try:
        with respx.mock(assert_all_called=False) as mock:
            mock.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=_hourly_payload()))
            mock.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=_archive_payload()))
            rc = await run_backtest()
    finally:
        os.chdir(cwd_before)
        os.environ.pop("LIMEN_BACKTEST_AOI", None)
        os.environ.pop("LIMEN_BACKTEST_START", None)
        os.environ.pop("LIMEN_BACKTEST_END", None)
    assert rc == 0
    reports_dir = tmp_path / "reports"
    assert reports_dir.exists()
    assert list(reports_dir.glob("backtest_*.md"))
