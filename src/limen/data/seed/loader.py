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


def _load_first_feature(file_name: str) -> SeedAOI:
    raw = resources.files(SEED_PACKAGE).joinpath(file_name).read_text(encoding="utf-8")
    fc = json.loads(raw)
    if fc.get("type") != "FeatureCollection" or not fc.get("features"):
        raise ValueError(f"Seed file {file_name} is not a non-empty FeatureCollection")

    feat = fc["features"][0]
    props = dict(feat.get("properties") or {})
    geom = shape(feat["geometry"])

    aoi_id = props.pop("id", None) or fc.get("name") or file_name
    name = props.pop("name", aoi_id)
    kind = props.pop("kind", "region")
    return SeedAOI(id=str(aoi_id), name=str(name), kind=str(kind), geom=geom, metadata=props)


def load_puglia() -> SeedAOI:
    return _load_first_feature("puglia_aoi.geojson")


def load_basilicata() -> SeedAOI:
    return _load_first_feature("basilicata_aoi.geojson")


def load_all() -> list[SeedAOI]:
    return [load_puglia(), load_basilicata()]
