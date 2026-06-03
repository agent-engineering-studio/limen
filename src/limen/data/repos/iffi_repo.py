"""IFFI landslide-inventory repository (stub).

Interface only. The actual ingest of the ISPRA IdroGEO / IFFI dataset is
implemented in a later prompt; this stub exists so neighbouring modules can
already type against it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shapely.geometry.base import BaseGeometry


@dataclass(frozen=True, slots=True)
class IFFILandslide:
    id: str
    movement_type: str | None
    state: str | None
    velocity_class: str | None
    geom: BaseGeometry
    attributes: dict[str, Any]


async def insert_landslide(_: IFFILandslide) -> None:  # pragma: no cover - stub
    raise NotImplementedError("IFFI ingest comes in a later prompt")


async def get_landslide(_: str) -> IFFILandslide | None:  # pragma: no cover - stub
    raise NotImplementedError("IFFI read comes in a later prompt")
