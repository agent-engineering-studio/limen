"""FastAPI HTTP integration tests via ASGITransport.

Uses the session-scoped Postgres testcontainer and the existing
``pg_pool`` fixture, then builds an app with
:class:`StubLlmClientFactory` and a minimal injected lifespan so the
scheduler isn't started here (it has its own test).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from shapely.geometry import Polygon

from limen.agents.llm_factory.stub import StubLlmClientFactory
from limen.api.dependencies import AppDependencies
from limen.api.main import build_app_with_deps
from limen.config.settings import Settings
from limen.data.db import acquire, get_pool
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
_AOI_ID = "e2e-bari-api"


@pytest.fixture(autouse=True)
async def _reset_http() -> None:
    await SharedHttpClient.aclose()
    yield
    await SharedHttpClient.aclose()


@pytest.fixture
async def app_client(reset_db: None, pg_pool: object) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings.model_validate({"enable_insitu": False})
    deps = await AppDependencies.build(
        pool=get_pool(),
        settings=settings,
        llm_factory=StubLlmClientFactory(),
    )
    app = build_app_with_deps(deps)
    # httpx.ASGITransport does not auto-fire FastAPI lifespan. For tests we
    # populate the state the lifespan would normally set; the production
    # lifespan path is exercised separately in ``test_api_lifespan.py``.
    app.state.deps = deps
    app.state.ready = True
    app.state.ready_detail = "test wiring"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _seed(aoi_id: str) -> None:
    await upsert_aoi(id=aoi_id, name="api test", kind="test", geom=_AOI)
    await generate_and_store_grid(aoi_id)
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cell_static_factors (cell_id)
            SELECT id FROM grid_cells WHERE aoi_id = $1
            ON CONFLICT (cell_id) DO NOTHING
            """,
            aoi_id,
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
    return {"daily": {"time": ["2026-05-31"], "precipitation_sum": [10.0]}}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
async def test_health_endpoint(app_client: httpx.AsyncClient) -> None:
    r = await app_client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["pool"] is True
    assert body["cache"] is True
    assert body["llm_provider"] == "stub"


async def test_ready_endpoint(app_client: httpx.AsyncClient) -> None:
    r = await app_client.get("/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert body["pool"] is True
    assert body["migrations"] is True


async def test_list_aoi(app_client: httpx.AsyncClient) -> None:
    await _seed(_AOI_ID)
    r = await app_client.get("/api/aoi")
    assert r.status_code == 200
    body = r.json()
    ids = {item["id"] for item in body["items"]}
    assert _AOI_ID in ids


async def test_monitor_endpoint_returns_full_assessment(app_client: httpx.AsyncClient) -> None:
    await _seed(_AOI_ID)
    with respx.mock(assert_all_called=False) as mock:
        mock.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=_hourly_payload()))
        mock.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=_archive_payload()))

        r = await app_client.post(f"/api/monitor/{_AOI_ID}", json={"cell_limit": 25})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["aoi_id"] == _AOI_ID
    assert body["cells_scored"] >= 1
    assert body["assessment"] is not None
    assert body["assessment"]["briefing_it"] is not None
    assert body["assessment"]["analysis"] is not None


async def test_monitor_unknown_aoi_returns_404(app_client: httpx.AsyncClient) -> None:
    r = await app_client.post("/api/monitor/does-not-exist", json={})
    assert r.status_code == 404


async def test_latest_assessment_after_monitor(app_client: httpx.AsyncClient) -> None:
    await _seed(_AOI_ID)
    with respx.mock(assert_all_called=False) as mock:
        mock.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=_hourly_payload()))
        mock.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=_archive_payload()))
        run = await app_client.post(f"/api/monitor/{_AOI_ID}", json={"cell_limit": 25})
    assert run.status_code == 200

    r = await app_client.get(f"/api/aoi/{_AOI_ID}/risk/latest")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["aoi_id"] == _AOI_ID
    assert body["cells"]
    assert body["briefing_it"] is not None


async def test_cell_breakdown_returns_jsonb(app_client: httpx.AsyncClient) -> None:
    await _seed(_AOI_ID)
    with respx.mock(assert_all_called=False) as mock:
        mock.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=_hourly_payload()))
        mock.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=_archive_payload()))
        run = await app_client.post(f"/api/monitor/{_AOI_ID}", json={"cell_limit": 25})
    assert run.status_code == 200
    cell_id = run.json()["assessment"]["top_cells"][0]["cell_id"]

    r = await app_client.get(f"/api/cell/{cell_id}/breakdown")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cell_id"] == cell_id
    assert "s" in body["factors"]
    assert "model_version" in body["explanation"]


async def test_alerts_endpoint(app_client: httpx.AsyncClient) -> None:
    await _seed(_AOI_ID)
    with respx.mock(assert_all_called=False) as mock:
        mock.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=_hourly_payload()))
        mock.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=_archive_payload()))
        await app_client.post(f"/api/monitor/{_AOI_ID}", json={"cell_limit": 25})

    r = await app_client.get("/api/alerts?threshold=None&since_hours=24")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["items"], list)


async def test_tiles_returns_503_when_unconfigured(app_client: httpx.AsyncClient) -> None:
    r = await app_client.get("/api/tiles/risk/10/512/512.pbf")
    assert r.status_code == 503
