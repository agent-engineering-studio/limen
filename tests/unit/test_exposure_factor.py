"""Shared alert-exposure factor — distance grading, fallback, YAML knobs."""

from __future__ import annotations

from pathlib import Path

import yaml

from limen.core.scoring.exposure import exposure_factor
from limen.core.scoring.regional_thresholds import (
    DEFAULT_THRESHOLDS_PATH,
    ExposureBlock,
    load_regional_thresholds,
)

_CFG = ExposureBlock()


def _factor(**kwargs: object) -> tuple[float, list[str]]:
    base: dict[str, object] = {
        "urban_here": False,
        "urban_near": False,
        "infra_here": False,
        "infra_near": False,
        "dist_road_m": None,
        "dist_rail_m": None,
        "road_class": None,
        "cfg": _CFG,
    }
    base.update(kwargs)
    return exposure_factor(**base)  # type: ignore[arg-type]


def test_no_exposure_is_zero() -> None:
    factor, tags = _factor()
    assert factor == 0.0
    assert tags == []


def test_road_distance_grading() -> None:
    strong, tags_strong = _factor(dist_road_m=180.0)
    medium, tags_medium = _factor(dist_road_m=800.0)
    none, tags_none = _factor(dist_road_m=5_000.0)
    assert strong == _CFG.road_strong
    assert medium == _CFG.road_medium
    assert none == 0.0
    assert strong > medium > none
    assert tags_strong == ["statale a 180 m"]
    assert tags_medium == ["statale a 800 m"]
    assert tags_none == []


def test_motorway_label_and_rail_tag() -> None:
    _, road_tags = _factor(dist_road_m=200.0, road_class="motorway")
    assert road_tags == ["autostrada a 200 m"]

    factor, rail_tags = _factor(dist_rail_m=950.0)
    assert factor == _CFG.rail_medium
    assert rail_tags == ["ferrovia a 950 m"]


def test_distance_formatting_edges() -> None:
    _, close = _factor(dist_road_m=40.0)
    assert close == ["statale a meno di 100 m"]
    wide = ExposureBlock(rail_medium_m=2_000.0)
    _, km = _factor(dist_rail_m=1_240.0, cfg=wide)
    assert km == ["ferrovia a 1,2 km"]


def test_corine_fallback_only_without_osm_distances() -> None:
    fallback, fallback_tags = _factor(infra_near=True)
    assert fallback == _CFG.infra_near_fallback
    assert fallback_tags == ["infrastrutture vicine"]

    # A known OSM distance (even a far one) disables the CORINE fallback.
    with_osm, with_osm_tags = _factor(infra_near=True, dist_road_m=30_000.0)
    assert with_osm == 0.0
    assert with_osm_tags == []


def test_urban_terms_and_cap() -> None:
    factor, tags = _factor(
        urban_here=True,
        dist_road_m=100.0,
        dist_rail_m=100.0,
    )
    assert factor == min(_CFG.urban_here + _CFG.road_strong + _CFG.rail_strong, _CFG.cap)
    assert tags[0] == "abitato"

    tiny_cap = ExposureBlock(cap=0.4)
    capped, _ = _factor(urban_here=True, dist_road_m=100.0, cfg=tiny_cap)
    assert capped == 0.4


def test_thresholds_come_from_yaml(tmp_path: Path) -> None:
    """Overriding the YAML block changes the factor — no hard-coded knobs."""
    cfg = yaml.safe_load(DEFAULT_THRESHOLDS_PATH.read_text(encoding="utf-8"))
    cfg["exposure"]["road_strong"] = 0.9
    cfg["exposure"]["road_strong_m"] = 500.0
    out = tmp_path / "tweaked.yaml"
    out.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    tweaked = load_regional_thresholds(out).exposure
    factor, _ = _factor(dist_road_m=400.0, cfg=tweaked)
    assert factor == 0.9


def test_yaml_without_exposure_block_still_validates(tmp_path: Path) -> None:
    cfg = yaml.safe_load(DEFAULT_THRESHOLDS_PATH.read_text(encoding="utf-8"))
    cfg.pop("exposure")
    out = tmp_path / "no_exposure.yaml"
    out.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    loaded = load_regional_thresholds(out)
    assert loaded.exposure == ExposureBlock()
