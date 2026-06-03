"""INGV client + sync_job tests (respx + testcontainers Postgres)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from limen.data.object_store.filesystem import FilesystemObjectStore
from limen.data.repos.raster_refs_repo import count as count_raster_refs
from limen.data.repos.seismic_repo import count_events, get_event
from limen.integrations._http import SharedHttpClient
from limen.integrations.ingv.shakemap_client import (
    FDSN_EVENT_URL,
    SHAKEMAP_GRID_URL_TEMPLATE,
    IngvHttpClient,
)
from limen.integrations.ingv.sync_job import run_ingv_sync

pytestmark = pytest.mark.integration

_PUGLIA_BBOX = (15.0, 39.85, 18.55, 42.0)


def _fdsn_feature(event_id: str, mag: float = 4.2) -> dict[str, object]:
    return {
        "type": "Feature",
        "id": event_id,
        "geometry": {"type": "Point", "coordinates": [16.5, 41.0, 12.3]},
        "properties": {
            "eventID": event_id,
            "time": "2026-05-30T12:34:56Z",
            "mag": mag,
            "magType": "Mlv",
            "place": "Murge meridionali",
        },
    }


def _fdsn_collection(features: list[dict[str, object]]) -> dict[str, object]:
    return {"type": "FeatureCollection", "features": features}


_FAKE_SHAKEMAP_XML = b"""<?xml version="1.0"?>
<shakemap_grid xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               event_id="ev-test-001"
               shakemap_id="ev-test-001"
               shakemap_version="1"
               event_type="ACTUAL">
  <event event_id="ev-test-001" magnitude="4.2" depth="12.3" lat="41.0" lon="16.5"/>
</shakemap_grid>
"""


@pytest.fixture(autouse=True)
async def _reset_http() -> None:
    await SharedHttpClient.aclose()
    yield
    await SharedHttpClient.aclose()


async def test_fetch_events_parses_features() -> None:
    with respx.mock(assert_all_called=True) as mock:
        mock.get(FDSN_EVENT_URL).mock(
            return_value=httpx.Response(
                200,
                json=_fdsn_collection([_fdsn_feature("ev-1", 4.0), _fdsn_feature("ev-2", 3.7)]),
            )
        )
        client = IngvHttpClient()
        feats = list(
            await client.fetch_events(
                bbox=_PUGLIA_BBOX,
                start=datetime(2026, 5, 29, tzinfo=UTC),
                end=datetime(2026, 6, 5, tzinfo=UTC),
            )
        )
    assert len(feats) == 2
    assert feats[0]["id"] == "ev-1"


async def test_fetch_events_handles_no_content() -> None:
    """FDSN sometimes returns 204 for empty windows — must yield []."""
    with respx.mock() as mock:
        mock.get(FDSN_EVENT_URL).mock(return_value=httpx.Response(204))
        client = IngvHttpClient()
        feats = list(
            await client.fetch_events(
                bbox=_PUGLIA_BBOX,
                start=datetime.now(UTC) - timedelta(days=7),
                end=datetime.now(UTC),
            )
        )
    assert feats == []


async def test_fetch_shakemap_grid_returns_bytes() -> None:
    event_id = "ev-test-001"
    with respx.mock() as mock:
        mock.get(SHAKEMAP_GRID_URL_TEMPLATE.format(event_id=event_id)).mock(
            return_value=httpx.Response(
                200,
                content=_FAKE_SHAKEMAP_XML,
                headers={"content-type": "application/xml"},
            )
        )
        client = IngvHttpClient()
        body = await client.fetch_shakemap_grid(event_id)
    assert body == _FAKE_SHAKEMAP_XML


async def test_fetch_shakemap_grid_404_returns_none() -> None:
    event_id = "ev-no-shakemap"
    with respx.mock() as mock:
        mock.get(SHAKEMAP_GRID_URL_TEMPLATE.format(event_id=event_id)).mock(
            return_value=httpx.Response(404)
        )
        client = IngvHttpClient()
        body = await client.fetch_shakemap_grid(event_id)
    assert body is None


async def test_fetch_events_degrades_to_empty(reset_db: None) -> None:
    with respx.mock() as mock:
        mock.get(FDSN_EVENT_URL).mock(return_value=httpx.Response(503))
        client = IngvHttpClient()
        feats = list(
            await client.fetch_events(
                bbox=_PUGLIA_BBOX,
                start=datetime.now(UTC) - timedelta(days=7),
                end=datetime.now(UTC),
            )
        )
    assert feats == []


async def test_run_ingv_sync_upserts_events_and_shakemap(
    reset_db: None,
    tmp_path: Path,
) -> None:
    """End-to-end: 2 events, 1 with ShakeMap → 2 events row + 1 raster_refs row."""
    event_with = "ev-test-001"
    event_without = "ev-test-002"

    with respx.mock(assert_all_called=False) as mock:
        mock.get(FDSN_EVENT_URL).mock(
            return_value=httpx.Response(
                200,
                json=_fdsn_collection(
                    [_fdsn_feature(event_with, 4.5), _fdsn_feature(event_without, 3.8)]
                ),
            )
        )
        mock.get(SHAKEMAP_GRID_URL_TEMPLATE.format(event_id=event_with)).mock(
            return_value=httpx.Response(200, content=_FAKE_SHAKEMAP_XML)
        )
        mock.get(SHAKEMAP_GRID_URL_TEMPLATE.format(event_id=event_without)).mock(
            return_value=httpx.Response(404)
        )

        store = FilesystemObjectStore(tmp_path)
        result = await run_ingv_sync(
            bbox=_PUGLIA_BBOX,
            lookback_days=14,
            min_magnitude=3.0,
            object_store=store,
        )

    assert result == {"events": 2, "shakemaps": 1}
    assert await count_events() == 2
    assert await count_raster_refs("shakemap_grid") == 1

    ev = await get_event(event_with)
    assert ev is not None
    assert ev.shakemap_path == f"shakemap/{event_with}/grid.xml"
    assert ev.raster_ref_id is not None
    assert (tmp_path / "shakemap" / event_with / "grid.xml").read_bytes() == _FAKE_SHAKEMAP_XML
