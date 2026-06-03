"""ISPRA IdroGEO sync_job tests — idempotency, parsing, repo writes."""

from __future__ import annotations

import httpx
import pytest
import respx
from shapely.geometry import Polygon

from limen.data.repos.aoi_repo import upsert_aoi
from limen.data.repos.iffi_repo import count_landslides, get_landslide
from limen.data.repos.pai_repo import count_pai
from limen.integrations._http import SharedHttpClient
from limen.integrations.idrogeo.client import DEFAULT_OWS_URL, IdroGeoHttpClient
from limen.integrations.idrogeo.sync_job import run_idrogeo_sync

pytestmark = pytest.mark.integration

_TEST_AOI_POLY = Polygon(
    [
        (16.86, 41.12),
        (16.92, 41.12),
        (16.92, 41.17),
        (16.86, 41.17),
        (16.86, 41.12),
    ]
)


def _iffi_point(iffi_id: str) -> dict[str, object]:
    return {
        "type": "Feature",
        "id": iffi_id,
        "geometry": {"type": "Point", "coordinates": [16.88, 41.14]},
        "properties": {
            "iffi_id": iffi_id,
            "movimento": "scivolamento",
            "stato": "attivo",
            "classe_velocita": "lenta",
            "data_evento": "2023-04-15",
        },
    }


def _iffi_poly(iffi_id: str) -> dict[str, object]:
    return {
        "type": "Feature",
        "id": iffi_id,
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [16.87, 41.13],
                    [16.89, 41.13],
                    [16.89, 41.15],
                    [16.87, 41.15],
                    [16.87, 41.13],
                ]
            ],
        },
        "properties": {
            "iffi_id": iffi_id,
            "movimento": "colata",
            "stato": "quiescente",
        },
    }


def _pai_feature(pai_id: str, hazard_class: str) -> dict[str, object]:
    return {
        "type": "Feature",
        "id": pai_id,
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [16.87, 41.13],
                    [16.89, 41.13],
                    [16.89, 41.15],
                    [16.87, 41.15],
                    [16.87, 41.13],
                ]
            ],
        },
        "properties": {
            "pai_id": pai_id,
            "classe_pai": hazard_class,
            "autorita_bacino": "Distretto Appennino Meridionale",
        },
    }


def _fc(features: list[dict[str, object]]) -> dict[str, object]:
    return {"type": "FeatureCollection", "features": features}


@pytest.fixture(autouse=True)
async def _reset_http() -> None:
    await SharedHttpClient.aclose()
    yield
    await SharedHttpClient.aclose()


def _wire_idrogeo_routes(mock: respx.MockRouter) -> None:
    """Wire WFS routes: layer is selected by the typeNames query parameter.

    We use the global DEFAULT_OWS_URL with respx URL prefix matching and
    distinguish layers by inspecting the request params in a side_effect.
    """

    def _route(request: httpx.Request) -> httpx.Response:
        tn = request.url.params.get("typeNames", "")
        if "iffi_punti" in tn:
            return httpx.Response(200, json=_fc([_iffi_point("iffi-001")]))
        if "iffi_aree" in tn:
            return httpx.Response(200, json=_fc([_iffi_poly("iffi-002")]))
        if "iffi_lineari" in tn:
            return httpx.Response(200, json=_fc([]))
        if "pai_pericolosita_frane" in tn:
            return httpx.Response(
                200,
                json=_fc([_pai_feature("pai-001", "P3"), _pai_feature("pai-002", "P1")]),
            )
        if "suscettibilita" in tn:
            return httpx.Response(200, json=_fc([]))
        return httpx.Response(404)

    mock.get(url__startswith=DEFAULT_OWS_URL).mock(side_effect=_route)


async def test_run_idrogeo_sync_upserts(reset_db: None) -> None:
    await upsert_aoi(
        id="test-bari-mini",
        name="Bari mini test AOI",
        kind="test",
        geom=_TEST_AOI_POLY,
    )
    with respx.mock() as mock:
        _wire_idrogeo_routes(mock)
        client = IdroGeoHttpClient()
        result = await run_idrogeo_sync(aoi_id="test-bari-mini", client=client)

    assert result["skipped"] is False
    assert result["iffi"] == 2
    assert result["pai"] == 2
    assert await count_landslides() == 2
    assert await count_pai() == 2

    ls = await get_landslide("iffi-001")
    assert ls is not None
    assert ls.movement_type == "scivolamento"
    assert ls.dataset_version_id is not None


async def test_run_idrogeo_sync_is_idempotent(reset_db: None) -> None:
    """Second run with identical WFS payloads must be a no-op (skipped)."""
    await upsert_aoi(
        id="test-bari-mini",
        name="Bari mini test AOI",
        kind="test",
        geom=_TEST_AOI_POLY,
    )
    with respx.mock() as mock:
        _wire_idrogeo_routes(mock)
        client = IdroGeoHttpClient()
        first = await run_idrogeo_sync(aoi_id="test-bari-mini", client=client)
        second = await run_idrogeo_sync(aoi_id="test-bari-mini", client=client)

    assert first["skipped"] is False
    assert first["iffi"] == 2
    assert second["skipped"] is True
    assert second["iffi"] == 0
    assert second["version"] == first["version"]
    # Totals unchanged after the second (no-op) sync.
    assert await count_landslides() == 2
    assert await count_pai() == 2


async def test_run_idrogeo_sync_handles_5xx(reset_db: None) -> None:
    """5xx on every WFS layer → empty payloads → no-op + recorded empty version."""
    await upsert_aoi(
        id="test-bari-mini",
        name="Bari mini test AOI",
        kind="test",
        geom=_TEST_AOI_POLY,
    )
    with respx.mock() as mock:
        mock.get(url__startswith=DEFAULT_OWS_URL).mock(return_value=httpx.Response(503))
        client = IdroGeoHttpClient()
        result = await run_idrogeo_sync(aoi_id="test-bari-mini", client=client)

    # All three layers degrade to []; total hash is empty payload, IFFI 0, PAI 0.
    assert result["iffi"] == 0
    assert result["pai"] == 0
    assert await count_landslides() == 0
    assert await count_pai() == 0
