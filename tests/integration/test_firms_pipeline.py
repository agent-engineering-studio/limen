"""FIRMS pipeline: idempotent ingest, post-fire window, event-driven trigger."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from pydantic import SecretStr
from shapely.geometry import MultiPolygon, box

from limen.agents.executors.fire_check import FireCheckExecutor
from limen.agents.llm_factory.stub import StubLlmClientFactory
from limen.api.dependencies import AppDependencies
from limen.api.jobs.firms_monitoring import run_firms_monitoring
from limen.config.settings import FirmsSettings, Settings
from limen.core.models.context import MonitoringContext
from limen.data.db import acquire, get_pool
from limen.data.repos.aoi_repo import upsert_aoi
from limen.data.repos.fire_repo import FireHotspot, count_hotspots, upsert_hotspots
from limen.data.repos.grid_repo import generate_and_store_grid
from limen.integrations._http import SharedHttpClient
from limen.integrations.firms import FirmsHttpClient, run_firms_sync
from limen.integrations.firms.client import DEFAULT_BASE_URL
from limen.integrations.openmeteo.client import ARCHIVE_URL, FORECAST_URL

pytestmark = pytest.mark.integration

_NATIONAL_BBOX = (6.0, 35.0, 19.0, 48.0)
_SOURCE = "VIIRS_SNPP_NRT"
_CSV_HEADER = (
    "country_id,latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,"
    "satellite,instrument,confidence,version,bright_ti5,frp,daynight"
)


@pytest.fixture(autouse=True)
async def _reset_http() -> None:
    await SharedHttpClient.aclose()
    yield
    await SharedHttpClient.aclose()


_AOI_ID = "firms-test-aoi"
# ~11x11 km inside Basilicata: a 1 km grid over it is ~120 cells, where
# seeding a real region would be ~20k for no extra coverage.
_AOI_BOUNDS = (16.40, 40.60, 16.50, 40.70)


async def _seed_test_aoi(*, with_grid: bool = False) -> tuple[str, float, float]:
    """Create the test AOI and return its id plus an interior point."""
    await upsert_aoi(
        id=_AOI_ID,
        name="FIRMS test AOI",
        kind="region",
        geom=MultiPolygon([box(*_AOI_BOUNDS)]),
        metadata={},
    )
    if with_grid:
        await generate_and_store_grid(_AOI_ID)
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT ST_Y(ST_PointOnSurface(geom)) AS lat,
                   ST_X(ST_PointOnSurface(geom)) AS lon
            FROM aoi WHERE id = $1
            """,
            _AOI_ID,
        )
    assert row is not None
    return _AOI_ID, float(row["lat"]), float(row["lon"])


def _hotspot_csv(*, lat: float, lon: float, times: tuple[str, ...]) -> str:
    day = datetime.now(UTC).date().isoformat()
    rows = [
        f"ITA,{lat},{lon},330.5,0.42,0.38,{day},{t},N,VIIRS,n,2.0NRT,295.1,15.0,D" for t in times
    ]
    return "\n".join([_CSV_HEADER, *rows]) + "\n"


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


async def _trim_grid(limit: int = 6) -> None:
    """Keep the workflow cheap: a handful of cells is enough to assert on."""
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cell_static_factors (cell_id)
            SELECT id FROM grid_cells
            ON CONFLICT (cell_id) DO NOTHING
            """
        )
        await conn.execute(
            "DELETE FROM grid_cells WHERE id NOT IN "
            "(SELECT id FROM grid_cells ORDER BY id LIMIT $1)",
            limit,
        )


def _firms_settings(*, min_hotspots: int = 2, cooldown_minutes: int = 90) -> Settings:
    return Settings(
        firms=FirmsSettings(
            map_key=SecretStr("test-key"),
            sources=[_SOURCE],
            min_hotspots=min_hotspots,
            cooldown_minutes=cooldown_minutes,
        ),
        # The flood feed is a separate opt-in pipeline with its own tests;
        # leaving it on here would only add unrelated HTTP to mock.
        enable_flood_forecast=False,
    )


async def _build_deps(settings: Settings | None = None) -> AppDependencies:
    return await AppDependencies.build(
        pool=get_pool(),
        settings=settings or Settings(),
        llm_factory=StubLlmClientFactory(),
    )


async def test_firms_sync_second_run_skips_all_writes(reset_db: None, pg_pool: object) -> None:
    """Idempotency: an unchanged FIRMS window is recognised by content hash."""
    csv_payload = _hotspot_csv(lat=40.5, lon=16.5, times=("1218", "1400"))
    client = FirmsHttpClient(map_key="test-key")

    with respx.mock() as mock:
        mock.get(url__startswith=DEFAULT_BASE_URL).mock(
            return_value=httpx.Response(200, text=csv_payload)
        )
        first = await run_firms_sync(client=client, bbox=_NATIONAL_BBOX, sources=[_SOURCE])
        second = await run_firms_sync(client=client, bbox=_NATIONAL_BBOX, sources=[_SOURCE])

    assert first["skipped"] is False
    assert first["hotspots"] == 2
    assert second["skipped"] is True
    assert second["hotspots"] == 0
    assert await count_hotspots() == 2


async def test_firms_sync_degrades_when_firms_is_unreachable(
    reset_db: None, pg_pool: object
) -> None:
    """A dead endpoint writes nothing and raises nothing."""
    client = FirmsHttpClient(map_key="test-key")
    with respx.mock() as mock:
        mock.get(url__startswith=DEFAULT_BASE_URL).mock(return_value=httpx.Response(401))
        result = await run_firms_sync(client=client, bbox=_NATIONAL_BBOX, sources=[_SOURCE])

    assert result["hotspots"] == 0
    assert await count_hotspots() == 0


async def test_hotspots_open_the_post_fire_window_without_an_effis_perimeter(
    reset_db: None, pg_pool: object
) -> None:
    """`months_since_fire` comes from FIRMS days before the perimeter exists."""
    aoi_id, lat, lon = await _seed_test_aoi()
    today = datetime.now(UTC).date()
    await upsert_hotspots(
        [
            FireHotspot(source=_SOURCE, acq_date=today, acq_time=t, latitude=lat, longitude=lon)
            for t in (1218, 1400, 1542)
        ]
    )
    ctx = MonitoringContext(aoi_id=aoi_id, valuation_time=datetime.now(UTC))

    updated = await FireCheckExecutor(min_hotspots=2).run(ctx)
    assert updated.months_since_fire == pytest.approx(0.0)

    # Below the clustering threshold the same detections must not count:
    # one flare or glint pixel is not a fire.
    strict = await FireCheckExecutor(min_hotspots=5).run(ctx)
    assert strict.months_since_fire is None


async def test_firms_monitoring_triggers_the_aoi_once_then_cools_down(
    reset_db: None, pg_pool: object
) -> None:
    aoi_id, lat, lon = await _seed_test_aoi(with_grid=True)
    await _trim_grid()
    deps = await _build_deps(_firms_settings())

    with respx.mock(assert_all_called=False) as mock:
        mock.get(url__startswith=DEFAULT_BASE_URL).mock(
            return_value=httpx.Response(
                200, text=_hotspot_csv(lat=lat, lon=lon, times=("1218", "1400"))
            )
        )
        mock.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=_hourly_payload()))
        mock.get(ARCHIVE_URL).mock(
            return_value=httpx.Response(
                200, json={"daily": {"time": ["2026-05-31"], "precipitation_sum": [10.0]}}
            )
        )
        first = await run_firms_monitoring(deps)
        second = await run_firms_monitoring(deps)

    assert aoi_id in first
    # The assessment the first run persisted is inside the cooldown window.
    assert second == {}


async def test_firms_monitoring_is_inert_without_a_map_key(reset_db: None, pg_pool: object) -> None:
    """Fail-closed: no key, no network call, no error."""
    await _seed_test_aoi()
    deps = await _build_deps(Settings(firms=FirmsSettings(map_key=None)))

    # respx raises on any unmocked request, and no route is registered:
    # the assertion is that the job never reaches the network.
    with respx.mock() as mock:
        result = await run_firms_monitoring(deps)

    assert result == {}
    assert not mock.calls
