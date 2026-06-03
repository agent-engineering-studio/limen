"""Open-Meteo client + cache-first wrapper tests.

Uses ``respx`` to mock the HTTP endpoints and ``testcontainers`` Postgres
(via the ``pg_pool`` / ``clean_cache`` fixtures) for the cache layer.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
import respx

from limen.data.caching.cached_openmeteo import CachedOpenMeteoClient
from limen.integrations._http import SharedHttpClient
from limen.integrations.openmeteo.client import (
    ARCHIVE_URL,
    FORECAST_URL,
    OpenMeteoHttpClient,
)

pytestmark = pytest.mark.integration


_PUGLIA_BBOX = (15.0, 39.85, 18.55, 42.0)


def _hourly_payload(hours: int = 4) -> dict[str, object]:
    base = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
    times = [(base + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(hours)]
    return {
        "latitude": 41.0,
        "longitude": 16.8,
        "generationtime_ms": 1.23,
        "hourly_units": {"precipitation": "mm", "soil_moisture_0_to_7cm": "m³/m³"},
        "hourly": {
            "time": times,
            "precipitation": [0.0, 1.5, 0.3, 0.0][:hours],
            "soil_moisture_0_to_7cm": [0.21, 0.22, 0.22, 0.21][:hours],
            "soil_moisture_7_to_28cm": [0.25, 0.25, 0.26, 0.26][:hours],
            "snowfall": [0.0, 0.0, 0.0, 0.0][:hours],
            "snow_depth": [0.0, 0.0, 0.0, 0.0][:hours],
        },
    }


def _archive_payload() -> dict[str, object]:
    return {
        "latitude": 41.0,
        "longitude": 16.8,
        "daily": {
            "time": ["2026-05-01", "2026-05-02", "2026-05-03"],
            "precipitation_sum": [2.0, 0.0, 7.5],
        },
    }


@pytest.fixture(autouse=True)
async def _reset_http() -> None:
    """Ensure the shared client is reset between respx routes."""
    await SharedHttpClient.aclose()
    yield
    await SharedHttpClient.aclose()


async def test_get_meteo_snapshot_parses_hourly() -> None:
    window_start = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
    window_end = datetime(2026, 6, 1, 3, 0, tzinfo=UTC)

    with respx.mock(assert_all_called=True) as mock:
        mock.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=_hourly_payload(4)))

        client = OpenMeteoHttpClient()
        snap = await client.get_meteo_snapshot(
            aoi_id="it-puglia",
            bbox=_PUGLIA_BBOX,
            window_start=window_start,
            window_end=window_end,
        )

    assert snap is not None
    assert len(snap.samples) == 4
    assert snap.total_precipitation_mm == pytest.approx(1.8, rel=1e-6)
    assert snap.max_soil_moisture_0_7_cm == pytest.approx(0.22, rel=1e-6)


async def test_get_api_returns_total_precip() -> None:
    with respx.mock(assert_all_called=True) as mock:
        mock.get(ARCHIVE_URL).mock(return_value=httpx.Response(200, json=_archive_payload()))

        client = OpenMeteoHttpClient()
        api = await client.get_api(
            aoi_id="it-puglia",
            bbox=_PUGLIA_BBOX,
            as_of=date(2026, 5, 3),
            days=3,
        )

    assert api == {"api_3d": pytest.approx(9.5, rel=1e-6)}


async def test_second_call_hits_cache(clean_cache: None) -> None:
    window_start = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
    window_end = datetime(2026, 6, 1, 3, 0, tzinfo=UTC)

    with respx.mock(assert_all_called=True) as mock:
        route = mock.get(FORECAST_URL).mock(
            return_value=httpx.Response(200, json=_hourly_payload(4))
        )

        cached = CachedOpenMeteoClient()
        first = await cached.get_meteo_snapshot(
            aoi_id="it-puglia",
            bbox=_PUGLIA_BBOX,
            window_start=window_start,
            window_end=window_end,
        )
        second = await cached.get_meteo_snapshot(
            aoi_id="it-puglia",
            bbox=_PUGLIA_BBOX,
            window_start=window_start,
            window_end=window_end,
        )

    assert first is not None
    assert second is not None
    assert route.call_count == 1  # second call served from cache
    assert second.total_precipitation_mm == first.total_precipitation_mm


async def test_degrades_gracefully_on_5xx() -> None:
    """A persistent server failure must yield None + log, not crash."""
    window_start = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
    window_end = datetime(2026, 6, 1, 1, 0, tzinfo=UTC)

    with respx.mock() as mock:
        mock.get(FORECAST_URL).mock(return_value=httpx.Response(503))

        client = OpenMeteoHttpClient()
        snap = await client.get_meteo_snapshot(
            aoi_id="it-puglia",
            bbox=_PUGLIA_BBOX,
            window_start=window_start,
            window_end=window_end,
        )

    assert snap is None


async def test_get_api_degrades_to_empty_dict() -> None:
    with respx.mock() as mock:
        mock.get(ARCHIVE_URL).mock(return_value=httpx.Response(503))

        client = OpenMeteoHttpClient()
        api = await client.get_api(
            aoi_id="it-puglia",
            bbox=_PUGLIA_BBOX,
            as_of=date(2026, 5, 3),
            days=30,
        )
    assert api == {}
