"""EFFIS bulk Shapefile fallback — download a ZIP, filter locally."""

from __future__ import annotations

import io
import zipfile
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from shapely.geometry import Polygon

from limen.integrations.effis.fire_client import (
    EffisHttpClient,
    _features_from_shapefile_zip,
    _filter_features,
    _parse_firedate,
)

_BULK_URL = "https://idrogeo.isprambiente.it/opendata/effis_perimeters_bulk.zip"


# ---------------------------------------------------------------------------
# Local filter helpers — no network
# ---------------------------------------------------------------------------
def test_parse_firedate_handles_iso_string() -> None:
    assert _parse_firedate("2024-08-15") == date(2024, 8, 15)


def test_parse_firedate_truncates_long_strings() -> None:
    assert _parse_firedate("2024-08-15T12:34:56Z") == date(2024, 8, 15)


def test_parse_firedate_none_or_invalid_returns_none() -> None:
    assert _parse_firedate(None) is None
    assert _parse_firedate("nope") is None


def _feature(props: dict[str, Any], coords: list[tuple[float, float]]) -> dict[str, Any]:
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "Polygon", "coordinates": [[*coords, coords[0]]]},
    }


def test_filter_features_by_date_range_inclusive() -> None:
    box = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    features = [
        _feature({"firedate": "2024-07-01"}, box),
        _feature({"firedate": "2024-08-15"}, box),
        _feature({"firedate": "2024-09-30"}, box),
    ]
    out = _filter_features(features, bbox=None, start=date(2024, 8, 1), end=date(2024, 8, 31))
    assert len(out) == 1
    assert out[0]["properties"]["firedate"] == "2024-08-15"


def test_filter_features_by_bbox_intersection() -> None:
    inside = _feature({"firedate": "2024-08-15"}, [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)])
    outside = _feature(
        {"firedate": "2024-08-15"}, [(10.0, 10.0), (11.0, 10.0), (11.0, 11.0), (10.0, 11.0)]
    )
    out = _filter_features([inside, outside], bbox=(0.5, 0.5, 0.6, 0.6), start=None, end=None)
    assert len(out) == 1
    assert out[0] is inside


def test_filter_features_drops_features_without_date_when_date_filter_active() -> None:
    box = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    no_date = _feature({"firedate": None}, box)
    out = _filter_features([no_date], bbox=None, start=date(2024, 1, 1), end=None)
    assert out == []


def test_filter_features_keeps_undated_features_when_no_date_filter() -> None:
    box = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    no_date = _feature({}, box)
    out = _filter_features([no_date], bbox=None, start=None, end=None)
    assert out == [no_date]


# ---------------------------------------------------------------------------
# _features_from_shapefile_zip — real shapefile, in-memory ZIP
# ---------------------------------------------------------------------------
def _make_effis_bulk_zip(tmp_path: Path) -> bytes:
    """Write a tiny ZIPped shapefile with two perimeters + firedate column."""
    import geopandas as gpd
    import pyogrio

    polys = [
        Polygon([(15.0, 41.0), (15.1, 41.0), (15.1, 41.1), (15.0, 41.1)]),
        Polygon([(16.0, 41.0), (16.1, 41.0), (16.1, 41.1), (16.0, 41.1)]),
    ]
    gdf = gpd.GeoDataFrame(
        {
            "id": ["A", "B"],
            "firedate": ["2024-07-15", "2024-08-15"],
        },
        geometry=polys,
        crs="EPSG:4326",
    )
    shp = tmp_path / "perimeters.shp"
    pyogrio.write_dataframe(gdf, str(shp), driver="ESRI Shapefile")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(tmp_path.glob("perimeters.*")):
            zf.write(path, arcname=path.name)
    return buf.getvalue()


def test_features_from_shapefile_zip_roundtrip(tmp_path: Path) -> None:
    payload = _make_effis_bulk_zip(tmp_path)
    features = _features_from_shapefile_zip(payload)
    assert len(features) == 2
    ids = {f["properties"]["id"] for f in features}
    assert ids == {"A", "B"}


def test_features_from_shapefile_zip_rejects_path_traversal(tmp_path: Path) -> None:
    """Refuse archives that try to escape the temp directory."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../escape.shp", b"\x00")
    with pytest.raises(ValueError, match="path-traversal"):
        _features_from_shapefile_zip(buf.getvalue())


def test_features_from_shapefile_zip_empty_archive_raises(tmp_path: Path) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", b"hi")
    with pytest.raises(ValueError, match=r"no \.shp file"):
        _features_from_shapefile_zip(buf.getvalue())


# ---------------------------------------------------------------------------
# End-to-end: respx + the bulk shapefile path
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@respx.mock
async def test_fetch_perimeters_bulk_filters_by_date(tmp_path: Path) -> None:
    payload = _make_effis_bulk_zip(tmp_path)
    respx.get(_BULK_URL).mock(return_value=httpx.Response(200, content=payload))

    client = EffisHttpClient()
    features = list(
        await client.fetch_perimeters_bulk(
            bulk_url=_BULK_URL,
            start=date(2024, 8, 1),
            end=date(2024, 9, 30),
        )
    )
    assert len(features) == 1
    assert features[0]["properties"]["id"] == "B"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_perimeters_bulk_degrades_on_5xx() -> None:
    respx.get(_BULK_URL).mock(return_value=httpx.Response(503))
    client = EffisHttpClient()
    features = list(await client.fetch_perimeters_bulk(bulk_url=_BULK_URL))
    assert features == []


@pytest.mark.asyncio
@respx.mock
async def test_fetch_perimeters_bulk_degrades_on_bad_archive() -> None:
    respx.get(_BULK_URL).mock(return_value=httpx.Response(200, content=b"not a zip"))
    client = EffisHttpClient()
    features = list(await client.fetch_perimeters_bulk(bulk_url=_BULK_URL))
    assert features == []
