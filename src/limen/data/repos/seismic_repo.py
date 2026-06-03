"""Seismic-events repository (INGV)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from shapely.geometry import Point

from limen.core.logging import get_logger
from limen.data.db import acquire

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SeismicEvent:
    id: str
    origin_time: datetime
    magnitude: float
    magnitude_type: str | None
    depth_km: float | None
    geom: Point
    region: str | None = None
    shakemap_path: str | None = None
    raster_ref_id: int | None = None
    dataset_version_id: int | None = None
    attributes: dict[str, Any] | None = None


async def upsert_event(event: SeismicEvent) -> None:
    """Insert-or-update a seismic event by INGV eventID."""
    attrs_json = json.dumps(event.attributes or {}, default=str)
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO seismic_events (
                id, origin_time, magnitude, magnitude_type, depth_km, geom, region,
                shakemap_path, raster_ref_id, dataset_version_id, attributes
            ) VALUES (
                $1, $2, $3, $4, $5, ST_SetSRID($6::geometry, 4326), $7, $8, $9, $10, $11::jsonb
            )
            ON CONFLICT (id) DO UPDATE
            SET origin_time    = EXCLUDED.origin_time,
                magnitude      = EXCLUDED.magnitude,
                magnitude_type = EXCLUDED.magnitude_type,
                depth_km       = EXCLUDED.depth_km,
                geom           = EXCLUDED.geom,
                region         = EXCLUDED.region,
                shakemap_path  = COALESCE(EXCLUDED.shakemap_path,
                                          seismic_events.shakemap_path),
                raster_ref_id  = COALESCE(EXCLUDED.raster_ref_id,
                                          seismic_events.raster_ref_id),
                dataset_version_id = COALESCE(EXCLUDED.dataset_version_id,
                                              seismic_events.dataset_version_id),
                attributes     = EXCLUDED.attributes,
                updated_at     = now()
            """,
            event.id,
            event.origin_time,
            event.magnitude,
            event.magnitude_type,
            event.depth_km,
            event.geom,
            event.region,
            event.shakemap_path,
            event.raster_ref_id,
            event.dataset_version_id,
            attrs_json,
        )


async def count_events() -> int:
    async with acquire() as conn:
        row = await conn.fetchrow("SELECT COUNT(*)::bigint AS n FROM seismic_events")
    return int(row["n"]) if row else 0


async def get_event(event_id: str) -> SeismicEvent | None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, origin_time, magnitude, magnitude_type, depth_km, geom,
                   region, shakemap_path, raster_ref_id, dataset_version_id, attributes
            FROM seismic_events WHERE id = $1
            """,
            event_id,
        )
    if row is None:
        return None
    attrs = row["attributes"]
    if isinstance(attrs, str):
        attrs = json.loads(attrs)
    return SeismicEvent(
        id=str(row["id"]),
        origin_time=row["origin_time"],
        magnitude=float(row["magnitude"]),
        magnitude_type=row["magnitude_type"],
        depth_km=float(row["depth_km"]) if row["depth_km"] is not None else None,
        geom=row["geom"],
        region=row["region"],
        shakemap_path=row["shakemap_path"],
        raster_ref_id=row["raster_ref_id"],
        dataset_version_id=row["dataset_version_id"],
        attributes=attrs or {},
    )
