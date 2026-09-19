"""Materialized-view + tiles-proxy integration tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from shapely.geometry import Polygon

from limen.agents.llm_factory.stub import StubLlmClientFactory
from limen.api.dependencies import AppDependencies
from limen.api.main import build_app_with_deps
from limen.config.settings import Settings
from limen.core.models.context import MonitoringContext
from limen.data.db import acquire, get_pool
from limen.data.repos.aoi_repo import upsert_aoi
from limen.data.repos.grid_repo import generate_and_store_grid
from limen.data.repos.map_views_repo import refresh_latest_risk
from limen.integrations._http import SharedHttpClient
from limen.integrations.openmeteo.client import ARCHIVE_URL, FORECAST_URL
from tests.conftest import register_flood_mocks

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
_AOI_ID = "mv-test-aoi"


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


@pytest.fixture(autouse=True)
async def _reset_http() -> None:
    await SharedHttpClient.aclose()
    yield
    await SharedHttpClient.aclose()


async def _seed_and_run_workflow(deps: AppDependencies) -> None:
    await upsert_aoi(id=_AOI_ID, name="mv test", kind="test", geom=_AOI)
    await generate_and_store_grid(_AOI_ID)
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cell_static_factors (cell_id)
            SELECT id FROM grid_cells WHERE aoi_id = $1
            ON CONFLICT (cell_id) DO NOTHING
            """,
            _AOI_ID,
        )
    workflow = deps.build_workflow()
    ctx = MonitoringContext(
        aoi_id=_AOI_ID,
        valuation_time=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
    )
    with respx.mock(assert_all_called=False) as mock:
        mock.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=_hourly_payload()))
        mock.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=_archive_payload()))
        # ENABLE_FLOOD_FORECAST defaults on, so the workflow also reaches GloFAS
        # and the marine API; without these routes respx raises inside the
        # executor and the sweep scores zero cells.
        register_flood_mocks(mock)
        await workflow.run(ctx)


async def test_mv_latest_risk_has_rows_after_monitor(reset_db: None, pg_pool: object) -> None:
    deps = await AppDependencies.build(
        pool=get_pool(),
        settings=Settings(),
        llm_factory=StubLlmClientFactory(),
    )
    await _seed_and_run_workflow(deps)

    async with acquire() as conn:
        n = await conn.fetchval(
            "SELECT COUNT(*) FROM mv_latest_risk WHERE aoi_id = $1",
            _AOI_ID,
        )
        with_score = await conn.fetchval(
            "SELECT COUNT(*) FROM mv_latest_risk WHERE aoi_id = $1 AND risk_score IS NOT NULL",
            _AOI_ID,
        )
    assert int(n) > 0
    assert int(with_score) > 0


async def test_refresh_latest_risk_returns_status(reset_db: None, pg_pool: object) -> None:
    """The SQL helper returns 1 (CONCURRENTLY) or 0 (first non-concurrent run)."""
    deps = await AppDependencies.build(
        pool=get_pool(),
        settings=Settings(),
        llm_factory=StubLlmClientFactory(),
    )
    await _seed_and_run_workflow(deps)
    # By now the workflow has already refreshed once → next call should be concurrent (1).
    code = await refresh_latest_risk()
    assert code in {0, 1}


async def test_tiles_are_proxied_not_redirected(reset_db: None, pg_pool: object) -> None:
    """I byte arrivano dall'API, e il nome interno di pg_tileserv non esce.

    Rimandare il browser a `http://pg_tileserv:7800` lasciava la mappa vuota:
    quel nome esiste solo dentro la rete Docker, e su una pagina https un salto
    in http viene bloccato a prescindere. Misurato in produzione: l'endpoint
    rispondeva 307 e nessuna cella compariva.
    """
    settings = Settings.model_validate({"api": {"pg_tileserv_url": "http://pg_tileserv:7800"}})
    deps = await AppDependencies.build(
        pool=get_pool(),
        settings=settings,
        llm_factory=StubLlmClientFactory(),
    )
    app = build_app_with_deps(deps)
    app.state.deps = deps
    app.state.ready = True
    app.state.ready_detail = "test"
    import respx

    tile = b"\x1a\x2f tile finta"
    with respx.mock(assert_all_called=True) as mock:
        rotta = mock.get("http://pg_tileserv:7800/mv_latest_risk/8/256/256.pbf").respond(
            200, content=tile, headers={"content-type": "application/x-protobuf"}
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/api/tiles/mv_latest_risk/8/256/256.pbf", follow_redirects=False)

    assert rotta.called
    assert r.status_code == 200
    assert r.content == tile
    assert r.headers["content-type"] == "application/x-protobuf"
    # Nessun redirect: il browser non deve mai vedere l'indirizzo interno.
    assert "location" not in r.headers


async def test_tiles_report_an_unreachable_tileserv(reset_db: None, pg_pool: object) -> None:
    """pg_tileserv giù è 502, non un errore attribuito al chiamante."""
    import respx

    settings = Settings.model_validate({"api": {"pg_tileserv_url": "http://pg_tileserv:7800"}})
    deps = await AppDependencies.build(
        pool=get_pool(),
        settings=settings,
        llm_factory=StubLlmClientFactory(),
    )
    app = build_app_with_deps(deps)
    app.state.deps = deps
    app.state.ready = True
    app.state.ready_detail = "test"

    with respx.mock as mock:
        mock.get(url__regex=r".*pg_tileserv.*").mock(side_effect=httpx.ConnectError("giù"))
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/api/tiles/risk/8/256/256.pbf")

    assert r.status_code == 502
