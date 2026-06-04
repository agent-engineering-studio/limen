"""Geo-Data Service — self-contained parsers (PAI class + IFFI attrs)."""

from __future__ import annotations

import pytest
from shapely.geometry import Polygon

from geodata.parsers import (
    PAI_CLASSES,
    ensure_valid,
    normalise_pai_class,
    parse_iffi_attributes,
    parse_pai_attributes,
    shape_from_geometry,
)


# ---------------------------------------------------------------------------
# normalise_pai_class
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("P1", "P1"),
        (" P3 ", "P3"),
        ("p2", "P2"),
        ("aa", "AA"),
        ("", "UNKNOWN"),
        (None, "UNKNOWN"),
        ("non_standard_string", "UNKNOWN"),
    ],
)
def test_normalise_pai_class(raw: str | None, expected: str) -> None:
    assert normalise_pai_class(raw) == expected


def test_pai_classes_contains_canonical_ladder() -> None:
    for cls in ("AA", "P1", "P2", "P3", "P4"):
        assert cls in PAI_CLASSES


# ---------------------------------------------------------------------------
# parse_iffi_attributes — aliasing tolerance
# ---------------------------------------------------------------------------
def test_parse_iffi_picks_first_id_alias() -> None:
    attrs = parse_iffi_attributes({"iffi_id": "ABC", "id_frana": "XYZ"})
    assert attrs["iffi_id"] == "ABC"


def test_parse_iffi_falls_back_through_aliases() -> None:
    attrs = parse_iffi_attributes({"idfrana": "FALLBACK"})
    assert attrs["iffi_id"] == "FALLBACK"


def test_parse_iffi_movement_aliases() -> None:
    a = parse_iffi_attributes({"movement": "scivolamento"})
    b = parse_iffi_attributes({"movimento": "colata"})
    c = parse_iffi_attributes({"mov_principale": "crollo"})
    assert a["movement_type"] == "scivolamento"
    assert b["movement_type"] == "colata"
    assert c["movement_type"] == "crollo"


def test_parse_iffi_returns_none_id_when_missing() -> None:
    attrs = parse_iffi_attributes({})
    assert attrs["iffi_id"] is None
    assert attrs["raw"] == {}


def test_parse_iffi_keeps_raw_attributes() -> None:
    src = {"iffi_id": "ABC", "stato": "attivo", "extras": "keep me"}
    attrs = parse_iffi_attributes(src)
    assert attrs["state"] == "attivo"
    assert attrs["raw"]["extras"] == "keep me"


# ---------------------------------------------------------------------------
# parse_pai_attributes
# ---------------------------------------------------------------------------
def test_parse_pai_picks_first_id_alias() -> None:
    attrs = parse_pai_attributes({"pai_id": "PAI-1"})
    assert attrs["pai_id"] == "PAI-1"


def test_parse_pai_normalises_class() -> None:
    attrs = parse_pai_attributes({"id_pai": "1", "classe_pai": "p3"})
    assert attrs["hazard_class"] == "P3"


def test_parse_pai_unknown_class_does_not_drop_row() -> None:
    attrs = parse_pai_attributes({"idpai": "ID", "pericolosita": "exotic"})
    assert attrs["pai_id"] == "ID"
    assert attrs["hazard_class"] == "UNKNOWN"


# ---------------------------------------------------------------------------
# shape_from_geometry — defensive
# ---------------------------------------------------------------------------
def test_shape_from_geometry_returns_none_on_missing() -> None:
    assert shape_from_geometry(None) is None
    assert shape_from_geometry({}) is None


def test_shape_from_geometry_validates_polygon() -> None:
    geom_field = {
        "type": "Polygon",
        "coordinates": [[[16.0, 41.0], [16.1, 41.0], [16.1, 41.1], [16.0, 41.1], [16.0, 41.0]]],
    }
    out = shape_from_geometry(geom_field)
    assert out is not None
    assert out.is_valid
    assert out.geom_type == "Polygon"


def test_ensure_valid_passes_through_valid_geometry() -> None:
    poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
    assert ensure_valid(poly) == poly
