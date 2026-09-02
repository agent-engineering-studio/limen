"""FIRMS client: CSV parsing, quality filter, URL shape, degradation."""

from __future__ import annotations

from datetime import UTC, date, datetime

import httpx
import pytest
import respx
from pydantic import SecretStr

from limen.config.settings import FirmsSettings
from limen.integrations._http import SharedHttpClient
from limen.integrations.firms.client import (
    DEFAULT_BASE_URL,
    FirmsHttpClient,
    parse_hotspot_csv,
)

_VIIRS_HEADER = (
    "country_id,latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,"
    "satellite,instrument,confidence,version,bright_ti5,frp,daynight"
)
_MODIS_HEADER = (
    "latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,"
    "instrument,confidence,version,bright_t31,frp,daynight"
)


def _viirs_csv(*rows: str) -> str:
    return "\n".join([_VIIRS_HEADER, *rows]) + "\n"


def _viirs_row(
    *,
    lat: float = 40.5,
    lon: float = 16.5,
    confidence: str = "n",
    frp: float = 12.7,
    acq_time: str = "1218",
) -> str:
    return (
        f"ITA,{lat},{lon},330.5,0.42,0.38,2026-08-15,{acq_time},N,VIIRS,"
        f"{confidence},2.0NRT,295.1,{frp},D"
    )


@pytest.fixture(autouse=True)
async def _reset_http() -> None:
    await SharedHttpClient.aclose()
    yield
    await SharedHttpClient.aclose()


def test_parse_extracts_the_detection_fields() -> None:
    hotspots = parse_hotspot_csv(_viirs_csv(_viirs_row()), source="VIIRS_SNPP_NRT")

    assert len(hotspots) == 1
    h = hotspots[0]
    assert h.source == "VIIRS_SNPP_NRT"
    assert h.acq_date == date(2026, 8, 15)
    assert h.acq_time == 1218
    assert (h.latitude, h.longitude) == (40.5, 16.5)
    assert h.frp_mw == pytest.approx(12.7)
    assert h.brightness_k == pytest.approx(330.5)
    assert h.confidence == "n"
    assert h.daynight == "D"
    assert h.instrument == "VIIRS"


def test_acquired_at_reads_acq_time_as_hhmm_utc() -> None:
    (early,) = parse_hotspot_csv(_viirs_csv(_viirs_row(acq_time="0118")), source="VIIRS_SNPP_NRT")
    assert early.acquired_at == datetime(2026, 8, 15, 1, 18, tzinfo=UTC)


def test_low_confidence_viirs_detections_are_dropped() -> None:
    csv_payload = _viirs_csv(
        _viirs_row(lat=40.1, confidence="l"),
        _viirs_row(lat=40.2, confidence="n"),
        _viirs_row(lat=40.3, confidence="h"),
    )
    kept = parse_hotspot_csv(csv_payload, source="VIIRS_SNPP_NRT", min_confidence="nominal")

    assert [h.latitude for h in kept] == [40.2, 40.3]


def test_min_confidence_high_keeps_only_high() -> None:
    csv_payload = _viirs_csv(
        _viirs_row(lat=40.2, confidence="nominal"),
        _viirs_row(lat=40.3, confidence="high"),
    )
    kept = parse_hotspot_csv(csv_payload, source="VIIRS_SNPP_NRT", min_confidence="high")

    assert [h.latitude for h in kept] == [40.3]


def test_modis_percentage_confidence_uses_the_pct_threshold() -> None:
    payload = "\n".join(
        [
            _MODIS_HEADER,
            "40.1,16.1,320.0,1.0,1.0,2026-08-15,1130,Terra,MODIS,20,6.1NRT,290.0,8.0,D",
            "40.2,16.2,340.0,1.0,1.0,2026-08-15,1130,Terra,MODIS,85,6.1NRT,300.0,25.0,D",
        ]
    )
    kept = parse_hotspot_csv(payload, source="MODIS_NRT", min_confidence_pct=50)

    assert [h.latitude for h in kept] == [40.2]


def test_frp_floor_drops_weak_detections() -> None:
    csv_payload = _viirs_csv(
        _viirs_row(lat=40.1, frp=0.9),
        _viirs_row(lat=40.2, frp=30.0),
    )
    kept = parse_hotspot_csv(csv_payload, source="VIIRS_SNPP_NRT", min_frp_mw=5.0)

    assert [h.latitude for h in kept] == [40.2]


def test_malformed_rows_are_skipped_not_fatal() -> None:
    payload = _viirs_csv(
        "ITA,not-a-number,16.5,330.5,0.4,0.4,2026-08-15,1218,N,VIIRS,n,2.0NRT,295.1,12.7,D",
        "ITA,40.5,16.5,330.5,0.4,0.4,not-a-date,1218,N,VIIRS,n,2.0NRT,295.1,12.7,D",
        _viirs_row(lat=40.9),
    )
    kept = parse_hotspot_csv(payload, source="VIIRS_SNPP_NRT")

    assert [h.latitude for h in kept] == [40.9]


def test_empty_response_yields_no_detections() -> None:
    assert parse_hotspot_csv(_VIIRS_HEADER + "\n", source="VIIRS_SNPP_NRT") == []


async def test_fetch_builds_the_documented_area_url() -> None:
    expected = f"{DEFAULT_BASE_URL}/test-key/VIIRS_SNPP_NRT/6,35,19,48/2/2026-08-15"
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get(expected).mock(
            return_value=httpx.Response(200, text=_viirs_csv(_viirs_row()))
        )
        client = FirmsHttpClient(map_key="test-key")
        hotspots = await client.fetch_hotspots(
            bbox=(6.0, 35.0, 19.0, 48.0),
            sources=["VIIRS_SNPP_NRT"],
            day_range=2,
            on_date=date(2026, 8, 15),
        )

    assert route.called
    assert len(hotspots) == 1


async def test_a_failing_source_does_not_lose_the_others() -> None:
    with respx.mock() as mock:
        mock.get(url__startswith=f"{DEFAULT_BASE_URL}/k/VIIRS_SNPP_NRT").mock(
            return_value=httpx.Response(401)
        )
        mock.get(url__startswith=f"{DEFAULT_BASE_URL}/k/VIIRS_NOAA20_NRT").mock(
            return_value=httpx.Response(200, text=_viirs_csv(_viirs_row(lat=41.0)))
        )
        client = FirmsHttpClient(map_key="k")
        hotspots = await client.fetch_hotspots(
            bbox=(6.0, 35.0, 19.0, 48.0),
            sources=["VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT"],
        )

    assert [h.latitude for h in hotspots] == [41.0]


async def test_bad_map_key_degrades_to_no_detections() -> None:
    with respx.mock() as mock:
        mock.get(url__startswith=DEFAULT_BASE_URL).mock(return_value=httpx.Response(401))
        client = FirmsHttpClient(map_key="wrong")
        hotspots = await client.fetch_hotspots(
            bbox=(6.0, 35.0, 19.0, 48.0), sources=["VIIRS_SNPP_NRT"]
        )

    assert hotspots == []


def test_feed_is_inactive_without_a_map_key() -> None:
    assert FirmsSettings().active is False
    assert FirmsSettings(map_key=SecretStr("abc")).active is True
    assert FirmsSettings(map_key=SecretStr("abc"), enabled=False).active is False
