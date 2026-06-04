"""Geo-Data Service — feature aggregation + PMTiles staging logic."""

from __future__ import annotations

import pytest

from geodata.exports.features import (
    IFFI_DENSITY_SATURATION,
    PAI_CLASS_NORMS,
    iffi_density,
    max_pai_norm,
)
from geodata.exports.pmtiles import _feature_to_json


# ---------------------------------------------------------------------------
# max_pai_norm
# ---------------------------------------------------------------------------
def test_pai_class_norms_cover_full_ladder() -> None:
    assert set(PAI_CLASS_NORMS.keys()) == {"AA", "P1", "P2", "P3", "P4"}
    # Monotone increase along the severity ladder.
    assert (
        PAI_CLASS_NORMS["AA"]
        < PAI_CLASS_NORMS["P1"]
        < PAI_CLASS_NORMS["P2"]
        < PAI_CLASS_NORMS["P3"]
        < PAI_CLASS_NORMS["P4"]
    )


def test_max_pai_norm_picks_most_severe() -> None:
    assert max_pai_norm(["AA", "P3", "P1"]) == PAI_CLASS_NORMS["P3"]


def test_max_pai_norm_case_insensitive() -> None:
    assert max_pai_norm(["aa", "p2"]) == PAI_CLASS_NORMS["P2"]


def test_max_pai_norm_ignores_unknown_classes() -> None:
    assert max_pai_norm(["mystery"]) is None
    assert max_pai_norm(["mystery", "P1"]) == PAI_CLASS_NORMS["P1"]


def test_max_pai_norm_empty() -> None:
    assert max_pai_norm([]) is None


# ---------------------------------------------------------------------------
# iffi_density
# ---------------------------------------------------------------------------
def test_iffi_density_zero_count_is_none() -> None:
    assert iffi_density(count=0) is None
    assert iffi_density(count=-3) is None


def test_iffi_density_saturates_at_one() -> None:
    assert iffi_density(count=int(IFFI_DENSITY_SATURATION)) == pytest.approx(1.0)
    assert iffi_density(count=int(IFFI_DENSITY_SATURATION) * 4) == pytest.approx(1.0)


def test_iffi_density_linear_below_saturation() -> None:
    assert iffi_density(count=1) == pytest.approx(1.0 / IFFI_DENSITY_SATURATION)
    assert iffi_density(count=2) == pytest.approx(2.0 / IFFI_DENSITY_SATURATION)


# ---------------------------------------------------------------------------
# PMTiles feature serialisation
# ---------------------------------------------------------------------------
class _Row(dict):
    """Stand-in for an asyncpg Record — supports ``row["key"]``."""

    pass


def test_feature_to_json_passes_properties_as_dict() -> None:
    row = _Row(
        id=42,
        properties={"hazard_class": "P3"},
        geometry={"type": "Point", "coordinates": [16.0, 41.0]},
    )
    out = _feature_to_json(row)
    assert '"hazard_class":"P3"' in out
    assert out.startswith('{"type":"Feature"')
    assert '"id":"42"' in out


def test_feature_to_json_decodes_string_props_and_geom() -> None:
    row = _Row(
        id="abc",
        properties='{"a": 1}',
        geometry='{"type":"Point","coordinates":[0,0]}',
    )
    out = _feature_to_json(row)
    assert '"a":1' in out
    assert '"type":"Point"' in out
