"""Helpers to load packaged seed AOIs from GeoJSON files."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from typing import Any

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

SEED_PACKAGE = "limen.data.seed"


@dataclass(frozen=True, slots=True)
class SeedAOI:
    id: str
    name: str
    kind: str
    geom: BaseGeometry
    metadata: dict[str, Any]


NATIONAL_FILE = "italy_regions_aoi.geojson"


def _feature_to_aoi(feat: dict[str, Any], *, fallback_id: str) -> SeedAOI:
    props = dict(feat.get("properties") or {})
    geom = shape(feat["geometry"])
    aoi_id = props.pop("id", None) or fallback_id
    name = props.pop("name", aoi_id)
    kind = props.pop("kind", "region")
    return SeedAOI(id=str(aoi_id), name=str(name), kind=str(kind), geom=geom, metadata=props)


def _load_features(file_name: str) -> list[SeedAOI]:
    raw = resources.files(SEED_PACKAGE).joinpath(file_name).read_text(encoding="utf-8")
    fc = json.loads(raw)
    if fc.get("type") != "FeatureCollection" or not fc.get("features"):
        raise ValueError(f"Seed file {file_name} is not a non-empty FeatureCollection")
    return [
        _feature_to_aoi(feat, fallback_id=f"{fc.get('name') or file_name}-{i}")
        for i, feat in enumerate(fc["features"])
    ]


def load_regions() -> list[SeedAOI]:
    """All 20 ISTAT regions (national seed)."""
    return _load_features(NATIONAL_FILE)


def _load_region(aoi_id: str) -> SeedAOI:
    for aoi in load_regions():
        if aoi.id == aoi_id:
            return aoi
    raise KeyError(f"region {aoi_id} not found in {NATIONAL_FILE}")


def load_puglia() -> SeedAOI:
    return _load_region("it-puglia")


def load_basilicata() -> SeedAOI:
    return _load_region("it-basilicata")


def load_all() -> list[SeedAOI]:
    return load_regions()
