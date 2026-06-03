"""EFFIS client + sync_job tests."""

from __future__ import annotations

import httpx
import pytest
import respx

from limen.data.repos.fire_repo import count_perimeters, get_perimeter
from limen.integrations._http import SharedHttpClient
from limen.integrations.effis.fire_client import DEFAULT_WFS_URL, EffisHttpClient
from limen.integrations.effis.sync_job import run_effis_sync

pytestmark = pytest.mark.integration

_PUGLIA_BBOX = (15.0, 39.85, 18.55, 42.0)


def _fire_feature(feat_id: str, area_ha: float = 12.5) -> dict[str, object]:
    return {
        "type": "Feature",
        "id": feat_id,
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [16.0, 40.2],
                    [16.05, 40.2],
                    [16.05, 40.25],
                    [16.0, 40.25],
                    [16.0, 40.2],
                ]
            ],
        },
        "properties": {
            "id": feat_id,
            "firedate": "2026-04-15",
            "area_ha": area_ha,
            "country": "IT",
            "province": "PZ",
        },
    }


def _fc(features: list[dict[str, object]]) -> dict[str, object]:
    return {"type": "FeatureCollection", "features": features}


@pytest.fixture(autouse=True)
async def _reset_http() -> None:
    await SharedHttpClient.aclose()
    yield
    await SharedHttpClient.aclose()


async def test_fetch_perimeters_parses() -> None:
    with respx.mock(assert_all_called=True) as mock:
        mock.get(url__startswith=DEFAULT_WFS_URL).mock(
            return_value=httpx.Response(
                200, json=_fc([_fire_feature("eu-1", 12.5), _fire_feature("eu-2", 7.0)])
            )
        )
        client = EffisHttpClient()
        feats = list(
            await client.fetch_perimeters(
                bbox=_PUGLIA_BBOX,
                start=__import__("datetime").date(2026, 1, 1),
                end=__import__("datetime").date(2026, 12, 31),
            )
        )
    assert len(feats) == 2
    assert feats[0]["id"] == "eu-1"


async def test_fetch_perimeters_degrades() -> None:
    with respx.mock() as mock:
        mock.get(url__startswith=DEFAULT_WFS_URL).mock(return_value=httpx.Response(503))
        client = EffisHttpClient()
        feats = list(
            await client.fetch_perimeters(
                bbox=_PUGLIA_BBOX,
                start=__import__("datetime").date(2026, 1, 1),
                end=__import__("datetime").date(2026, 12, 31),
            )
        )
    assert feats == []


async def test_run_effis_sync_upserts(reset_db: None) -> None:
    with respx.mock() as mock:
        mock.get(url__startswith=DEFAULT_WFS_URL).mock(
            return_value=httpx.Response(
                200, json=_fc([_fire_feature("eu-1", 12.5), _fire_feature("eu-2", 7.0)])
            )
        )
        result = await run_effis_sync(bbox=_PUGLIA_BBOX, lookback_days=365)

    assert result == {"perimeters": 2, "dnbr_stored": 0}
    assert await count_perimeters() == 2

    p = await get_perimeter("eu-1")
    assert p is not None
    assert p.area_ha == pytest.approx(12.5)
    assert p.fire_date is not None
    assert p.fire_date.isoformat() == "2026-04-15"
