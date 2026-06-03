"""Burnt-area perimeters repository (EFFIS)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

from limen.core.logging import get_logger
from limen.data.db import acquire

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class FirePerimeter:
    id: str
    fire_date: date | None
    area_ha: float | None
    country: str | None
    province: str | None
    geom: MultiPolygon
    dnbr_path: str | None = None
    raster_ref_id: int | None = None
    dataset_version_id: int | None = None
    attributes: dict[str, Any] | None = None


def _as_multipolygon(geom: BaseGeometry) -> MultiPolygon:
    if isinstance(geom, MultiPolygon):
        return geom
    if isinstance(geom, Polygon):
        return MultiPolygon([geom])
    raise TypeError(f"FirePerimeter geometry must be (Multi)Polygon, got {type(geom).__name__}")


async def upsert_perimeter(perimeter: FirePerimeter) -> None:
    """Insert-or-update a burnt-area perimeter by EFFIS feature id."""
    attrs_json = json.dumps(perimeter.attributes or {}, default=str)
    multi = _as_multipolygon(perimeter.geom)
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO fire_perimeters (
                id, fire_date, area_ha, country, province, geom,
                dnbr_path, raster_ref_id, dataset_version_id, attributes
            ) VALUES (
                $1, $2, $3, $4, $5, ST_SetSRID($6::geometry, 4326),
                $7, $8, $9, $10::jsonb
            )
            ON CONFLICT (id) DO UPDATE
            SET fire_date     = EXCLUDED.fire_date,
                area_ha       = EXCLUDED.area_ha,
                country       = EXCLUDED.country,
                province      = EXCLUDED.province,
                geom          = EXCLUDED.geom,
                dnbr_path     = COALESCE(EXCLUDED.dnbr_path,
                                         fire_perimeters.dnbr_path),
                raster_ref_id = COALESCE(EXCLUDED.raster_ref_id,
                                         fire_perimeters.raster_ref_id),
                dataset_version_id = COALESCE(EXCLUDED.dataset_version_id,
                                              fire_perimeters.dataset_version_id),
                attributes    = EXCLUDED.attributes,
                updated_at    = now()
            """,
            perimeter.id,
            perimeter.fire_date,
            perimeter.area_ha,
            perimeter.country,
            perimeter.province,
            multi,
            perimeter.dnbr_path,
            perimeter.raster_ref_id,
            perimeter.dataset_version_id,
            attrs_json,
        )


async def count_perimeters() -> int:
    async with acquire() as conn:
        row = await conn.fetchrow("SELECT COUNT(*)::bigint AS n FROM fire_perimeters")
    return int(row["n"]) if row else 0


async def get_perimeter(perimeter_id: str) -> FirePerimeter | None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, fire_date, area_ha, country, province, geom,
                   dnbr_path, raster_ref_id, dataset_version_id, attributes
            FROM fire_perimeters WHERE id = $1
            """,
            perimeter_id,
        )
    if row is None:
        return None
    attrs = row["attributes"]
    if isinstance(attrs, str):
        attrs = json.loads(attrs)
    return FirePerimeter(
        id=str(row["id"]),
        fire_date=row["fire_date"],
        area_ha=float(row["area_ha"]) if row["area_ha"] is not None else None,
        country=row["country"],
        province=row["province"],
        geom=row["geom"],
        dnbr_path=row["dnbr_path"],
        raster_ref_id=row["raster_ref_id"],
        dataset_version_id=row["dataset_version_id"],
        attributes=attrs or {},
    )
