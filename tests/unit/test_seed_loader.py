"""Packaged GeoJSON seeds load and parse to valid Shapely geometries."""

from __future__ import annotations

from shapely.geometry import MultiPolygon, Polygon

from limen.data.seed.loader import load_all, load_basilicata, load_puglia


def test_load_puglia_returns_polygon_or_multipolygon() -> None:
    aoi = load_puglia()
    assert aoi.id == "it-puglia"
    assert isinstance(aoi.geom, MultiPolygon | Polygon)
    assert aoi.geom.is_valid
    assert aoi.geom.area > 0


def test_load_basilicata_returns_polygon_or_multipolygon() -> None:
    aoi = load_basilicata()
    assert aoi.id == "it-basilicata"
    assert isinstance(aoi.geom, MultiPolygon | Polygon)
    assert aoi.geom.is_valid


def test_load_all_returns_both() -> None:
    aois = load_all()
    assert {a.id for a in aois} == {"it-puglia", "it-basilicata"}
