"""Dated landslide-event repository (ITALICA / e-ITALICA truth set).

Idempotent ``upsert_many`` keyed by the catalogue id, so re-ingesting the
same CSV is a no-op. Distinct from :mod:`limen.data.repos.iffi_repo`: these
are point events with a timestamp, used by the §2.5 backtest, not the
polygon inventory that feeds the S component.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from shapely.geometry.base import BaseGeometry

from limen.core.logging import get_logger
from limen.data.db import acquire

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class LandslideEvent:
    id: str
    source: str
    event_time: datetime
    geom: BaseGeometry
    temporal_accuracy: str | None = None
    geographic_accuracy: str | None = None
    landslide_type: str | None = None
    region: str | None = None
    province: str | None = None
    municipality: str | None = None
    elevation_m: float | None = None
    slope_deg: float | None = None
    duration_h: float | None = None
    cumulated_rainfall_mm: float | None = None
    attributes: dict[str, Any] | None = None


async def upsert_many(items: Iterable[LandslideEvent]) -> int:
    """Insert-or-update each event by id, in a single transaction."""
    items_list = list(items)
    if not items_list:
        return 0

    async with acquire() as conn, conn.transaction():
        for e in items_list:
            attrs_json = json.dumps(e.attributes or {}, default=str)
            await conn.execute(
                """
                INSERT INTO landslide_events (
                    id, source, event_time, temporal_accuracy, geographic_accuracy,
                    landslide_type, region, province, municipality, elevation_m,
                    slope_deg, duration_h, cumulated_rainfall_mm, geom, attributes
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
                    ST_SetSRID($14::geometry, 4326), $15::jsonb
                )
                ON CONFLICT (id) DO UPDATE
                SET source                = EXCLUDED.source,
                    event_time            = EXCLUDED.event_time,
                    temporal_accuracy     = EXCLUDED.temporal_accuracy,
                    geographic_accuracy   = EXCLUDED.geographic_accuracy,
                    landslide_type        = EXCLUDED.landslide_type,
                    region                = EXCLUDED.region,
                    province              = EXCLUDED.province,
                    municipality          = EXCLUDED.municipality,
                    elevation_m           = EXCLUDED.elevation_m,
                    slope_deg             = EXCLUDED.slope_deg,
                    duration_h            = EXCLUDED.duration_h,
                    cumulated_rainfall_mm = EXCLUDED.cumulated_rainfall_mm,
                    geom                  = EXCLUDED.geom,
                    attributes            = EXCLUDED.attributes
                """,
                e.id,
                e.source,
                e.event_time,
                e.temporal_accuracy,
                e.geographic_accuracy,
                e.landslide_type,
                e.region,
                e.province,
                e.municipality,
                e.elevation_m,
                e.slope_deg,
                e.duration_h,
                e.cumulated_rainfall_mm,
                e.geom,
                attrs_json,
            )
    log.info("landslide_events.upsert_many", count=len(items_list))
    return len(items_list)


async def count_events() -> int:
    async with acquire() as conn:
        row = await conn.fetchrow("SELECT COUNT(*)::bigint AS n FROM landslide_events")
    return int(row["n"]) if row else 0
