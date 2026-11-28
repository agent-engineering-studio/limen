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


async def test_the_two_layers_never_mix(reset_db: None) -> None:
    """Rows of both EFFIS layers can share an id; readers see only Limen's (#714)."""
    from limen.data.db import acquire
    from limen.data.repos.fire_repo import PERIMETER_LAYER

    envelope = "ST_Multi(ST_MakeEnvelope(16.0, 40.2, 16.05, 40.25, 4326))"
    async with acquire() as conn:
        for layer in ("nrt.ba.poly", "ms:modis.ba.poly"):
            await conn.execute(
                "INSERT INTO fire_perimeters (layer, id, fire_date, area_ha, geom) "
                f"VALUES ($1, 'same-id', '2026-08-01', 10, {envelope})",
                layer,
            )
        with pytest.raises(Exception, match='null value in column "layer"'):
            await conn.execute(
                f"INSERT INTO fire_perimeters (id, geom) VALUES ('no-layer', {envelope})"
            )
        with pytest.raises(Exception, match="fire_perimeters_layer_check"):
            await conn.execute(
                "INSERT INTO fire_perimeters (layer, id, geom) "
                f"VALUES ('effis:other', 'x', {envelope})"
            )
        seen = await conn.fetch("SELECT DISTINCT layer FROM v_fire_perimeters")
    assert [r["layer"] for r in seen] == [PERIMETER_LAYER] == ["ms:modis.ba.poly"]
    assert await count_perimeters() == 1
    assert await count_perimeters(layer="nrt.ba.poly") == 1


async def test_sync_stores_the_richer_layer(reset_db: None) -> None:
    feature = _fire_feature("modis-1")
    feature["properties"] = {
        "id": "modis-1",
        "FIREDATE": "2026-09-13 11:00:00",
        "FINALDATE": "2026-09-14 10:00:00",
        "LASTUPDATE": "2026-09-18 08:00:00",
        "COUNTRY": "IT",
        "PROVINCE": "Matera",
        "COMMUNE": "Matera",
        "AREA_HA": "67",
        "AGRIAREAS": "59.7",
        "OTHERNATLC": "38.8",
        "TRANSIT": "1.5",
        "BROADLEA": "0",
        "PERCNA2K": "0",
    }
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get(url__startswith=DEFAULT_WFS_URL).mock(
            return_value=httpx.Response(200, json=_fc([feature]))
        )
        counts = await run_effis_sync(bbox=_PUGLIA_BBOX, lookback_days=3650)
    assert counts["perimeters"] == 1
    assert route.calls.last.request.url.params["typename"] == "ms:modis.ba.poly"
    assert str(route.calls.last.request.url).startswith(
        "https://maps.effis.emergency.copernicus.eu/effis"
    )
    stored = await get_perimeter("modis-1")
    assert stored is not None
    assert stored.layer == "ms:modis.ba.poly"
    assert stored.area_ha == 67.0
    assert stored.municipality == "Matera"
    assert str(stored.last_update) == "2026-09-18"
    assert stored.land_cover_pct == {
        "agriculture": 59.7,
        "other_natural": 38.8,
        "transitional": 1.5,
        "broadleaved_forest": 0.0,
    }
    assert stored.natura2000_pct == 0.0
