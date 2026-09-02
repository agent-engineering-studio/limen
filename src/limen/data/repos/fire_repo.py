"""Fire repository — EFFIS burnt-area perimeters + FIRMS active-fire hotspots."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
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


# ---------------------------------------------------------------------------
# FIRMS active-fire hotspots (point detections, NRT + archive)
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class FireHotspot:
    """One FIRMS detection. The first five fields are its natural key."""

    source: str
    acq_date: date
    acq_time: int
    latitude: float
    longitude: float
    frp_mw: float | None = None
    confidence: str | None = None
    brightness_k: float | None = None
    daynight: str | None = None
    satellite: str | None = None
    instrument: str | None = None

    @property
    def acquired_at(self) -> datetime:
        """UTC acquisition instant; FIRMS reports ``acq_time`` as HHMM UTC."""
        return datetime(
            self.acq_date.year,
            self.acq_date.month,
            self.acq_date.day,
            self.acq_time // 100,
            self.acq_time % 100,
            tzinfo=UTC,
        )


_UPSERT_HOTSPOT_SQL = """
INSERT INTO fire_hotspots (
    source, acq_date, acq_time, latitude, longitude, acquired_at,
    frp_mw, confidence, brightness_k, daynight, satellite, instrument,
    geom, dataset_version_id
) VALUES (
    $1, $2, $3, $4, $5, $6,
    $7, $8, $9, $10, $11, $12,
    ST_SetSRID(ST_MakePoint($5, $4), 4326), $13
)
ON CONFLICT (source, acq_date, acq_time, latitude, longitude) DO UPDATE
SET frp_mw             = EXCLUDED.frp_mw,
    confidence         = EXCLUDED.confidence,
    brightness_k       = EXCLUDED.brightness_k,
    daynight           = EXCLUDED.daynight,
    satellite          = EXCLUDED.satellite,
    instrument         = EXCLUDED.instrument,
    dataset_version_id = COALESCE(EXCLUDED.dataset_version_id,
                                  fire_hotspots.dataset_version_id),
    updated_at         = now()
"""


async def upsert_hotspots(
    hotspots: Sequence[FireHotspot],
    *,
    dataset_version_id: int | None = None,
) -> int:
    """Insert-or-update hotspots by natural key. Returns the row count written."""
    if not hotspots:
        return 0
    rows = [
        (
            h.source,
            h.acq_date,
            h.acq_time,
            h.latitude,
            h.longitude,
            h.acquired_at,
            h.frp_mw,
            h.confidence,
            h.brightness_k,
            h.daynight,
            h.satellite,
            h.instrument,
            dataset_version_id,
        )
        for h in hotspots
    ]
    async with acquire() as conn:
        await conn.executemany(_UPSERT_HOTSPOT_SQL, rows)
    return len(rows)


async def count_hotspots() -> int:
    async with acquire() as conn:
        row = await conn.fetchrow("SELECT COUNT(*)::bigint AS n FROM fire_hotspots")
    return int(row["n"]) if row else 0


async def aoi_hotspot_counts(*, window_hours: int, min_hotspots: int) -> dict[str, int]:
    """AOIs with at least ``min_hotspots`` detections in the trailing window.

    The AOI polygon (not its bbox) decides containment, so a hotspot just
    outside the region never triggers it.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT a.id AS aoi_id, COUNT(*)::bigint AS n
            FROM aoi a
            JOIN fire_hotspots fh ON ST_Intersects(a.geom, fh.geom)
            WHERE fh.acquired_at >= now() - make_interval(hours => $1)
            GROUP BY a.id
            HAVING COUNT(*) >= $2
            ORDER BY a.id
            """,
            window_hours,
            min_hotspots,
        )
    return {str(r["aoi_id"]): int(r["n"]) for r in rows}
