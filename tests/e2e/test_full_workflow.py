"""End-to-end MAF workflow test.

Spins up testcontainers Postgres, seeds a tiny AOI + grid, mocks
Open-Meteo via respx, runs the full landslide workflow with a
:class:`StubLlmClientFactory`, and asserts the persisted
``risk_assessments`` row + structured assessment.

Also covers the **invariance** guarantee: the numeric ``cell_results``
are identical whether or not the LLM nodes are included.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from shapely.geometry import Polygon

from limen.agents.llm_factory.stub import StubLlmClientFactory
from limen.agents.workflows.main_workflow import (
    WorkflowDeps,
    build_landslide_workflow,
)
from limen.config.settings import Settings
from limen.core.models.context import MonitoringContext
from limen.data.db import acquire
from limen.data.repos.aoi_repo import upsert_aoi
from limen.data.repos.grid_repo import generate_and_store_grid
from limen.integrations._http import SharedHttpClient
from limen.integrations.openmeteo.client import ARCHIVE_URL, FORECAST_URL

pytestmark = pytest.mark.integration

_AOI = Polygon(
    [
        (16.86, 41.12),
        (16.92, 41.12),
        (16.92, 41.17),
        (16.86, 41.17),
        (16.86, 41.12),
    ]
)


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
    return {
        "daily": {
            "time": ["2026-05-31"],
            "precipitation_sum": [12.0],
        },
    }


@pytest.fixture(autouse=True)
async def _reset_http() -> None:
    await SharedHttpClient.aclose()
    yield
    await SharedHttpClient.aclose()


async def _seed_minimal_aoi(aoi_id: str) -> None:
    await upsert_aoi(id=aoi_id, name="e2e test", kind="test", geom=_AOI)
    await generate_and_store_grid(aoi_id)
    # Pre-seed empty cell_static_factors rows for every grid cell so the
    # StaticFactors executor finds them.
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cell_static_factors (cell_id)
            SELECT id FROM grid_cells WHERE aoi_id = $1
            ON CONFLICT (cell_id) DO NOTHING
            """,
            aoi_id,
        )


async def _run_workflow(
    *,
    aoi_id: str,
    enable_insitu: bool = False,
    canned_briefing: list[str] | None = None,
) -> MonitoringContext:
    with respx.mock(assert_all_called=False) as mock:
        mock.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=_hourly_payload()))
        mock.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=_archive_payload()))

        factory = StubLlmClientFactory(
            canned_by_role={"Briefing": canned_briefing} if canned_briefing else {},
        )
        deps = WorkflowDeps(
            llm_factory=factory,
            settings=Settings.model_validate({"enable_insitu": enable_insitu}),
        )
        wf = build_landslide_workflow(deps)
        ctx = MonitoringContext(
            aoi_id=aoi_id,
            valuation_time=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
            enable_insitu=enable_insitu,
        )
        result = await wf.run(ctx)
    return result.context


async def test_full_workflow_runs_end_to_end(reset_db: None) -> None:
    aoi_id = "e2e-bari-mini"
    await _seed_minimal_aoi(aoi_id)

    out = await _run_workflow(aoi_id=aoi_id)

    # All 10 (non-IoT) stages produced output
    assert out.bbox is not None
    assert len(out.cell_ids) > 0
    assert len(out.cell_results) == len(out.cell_ids)
    assert out.assessment is not None
    assert out.assessment.briefing_it is not None
    assert out.assessment.analysis is not None
    # The briefing is in Italian and in the expected word window
    assert (
        "modello" in out.assessment.briefing_it.lower()
        or "rischio" in out.assessment.briefing_it.lower()
    )

    # Persisted: one risk_assessments row per cell
    async with acquire() as conn:
        n = await conn.fetchval(
            "SELECT COUNT(*) FROM risk_assessments WHERE cell_id IN ("
            "SELECT id FROM grid_cells WHERE aoi_id = $1)",
            aoi_id,
        )
    assert int(n) == len(out.cell_ids)


async def test_enable_insitu_inserts_sensor_fetch_step(reset_db: None) -> None:
    """With the IoT branch on, the workflow still completes.

    V1.5 — the executor now actually reads ``sensor_features_hourly``.
    On an unseeded DB it finds no features (empty dict), the engine
    runs the pure V1 path, and downstream nodes (briefing, persist)
    behave exactly like the V1 case.
    """
    aoi_id = "e2e-bari-insitu"
    await _seed_minimal_aoi(aoi_id)
    out = await _run_workflow(aoi_id=aoi_id, enable_insitu=True)

    assert out.sensor_payload is not None
    assert out.sensor_payload.get("source") == "sensor_features_hourly"
    assert out.sensor_payload.get("cells_with_features") == 0
    assert out.sensor_features_by_cell == {}
    assert out.assessment is not None
    assert out.assessment.briefing_it is not None
    # Invariance: with no in-situ rows, every cell is unmonitored and
    # hard_escalation stays false.
    assert all(not r.monitored for r in out.cell_results)
    assert all(not r.hard_escalation for r in out.cell_results)


async def test_llm_does_not_change_numeric_breakdown(reset_db: None) -> None:
    """Running the workflow twice with *different* LLM canned responses must
    yield identical numeric ``cell_results`` (the LLM is non-authoritative)."""
    aoi_id = "e2e-bari-invariance"
    await _seed_minimal_aoi(aoi_id)

    first = await _run_workflow(aoi_id=aoi_id)
    second = await _run_workflow(
        aoi_id=aoi_id,
        canned_briefing=[" ".join(["alfa"] * 200)],  # different briefing text
    )

    assert len(first.cell_results) == len(second.cell_results)
    for r1, r2 in zip(first.cell_results, second.cell_results, strict=True):
        assert r1.cell_id == r2.cell_id
        assert r1.score == pytest.approx(r2.score, abs=1e-12)
        assert r1.level == r2.level
        assert r1.s == pytest.approx(r2.s, abs=1e-12)
        assert r1.m == pytest.approx(r2.m, abs=1e-12)
        assert r1.e == pytest.approx(r2.e, abs=1e-12)
        assert r1.f == pytest.approx(r2.f, abs=1e-12)
        assert r1.h == pytest.approx(r2.h, abs=1e-12)
