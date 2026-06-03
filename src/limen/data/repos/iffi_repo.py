"""IFFI landslide-inventory repository.

Implemented enough to support the ISPRA IdroGEO sync job: idempotent
``upsert_many`` keyed by IFFI id, transactional, with optional
``dataset_version_id`` linkage for reproducibility.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any

from shapely.geometry.base import BaseGeometry
from shapely.validation import make_valid

from limen.core.logging import get_logger
from limen.data.db import acquire

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class IFFILandslide:
    id: str
    movement_type: str | None
    state: str | None
    velocity_class: str | None
    occurrence_date: date | None
    geom: BaseGeometry
    dataset_version_id: int | None = None
    attributes: dict[str, Any] | None = None


def _ensure_valid(geom: BaseGeometry) -> BaseGeometry:
    return geom if geom.is_valid else make_valid(geom)


async def upsert_many(items: Iterable[IFFILandslide]) -> int:
    """Insert-or-update each item by id, in a single transaction.

    Returns the count of rows processed.
    """
    items_list = list(items)
    if not items_list:
        return 0

    async with acquire() as conn, conn.transaction():
        for item in items_list:
            geom = _ensure_valid(item.geom)
            attrs_json = json.dumps(item.attributes or {}, default=str)
            await conn.execute(
                """
                INSERT INTO iffi_landslides (
                    id, movement_type, state, velocity_class, occurrence_date,
                    geom, dataset_version_id, attributes
                ) VALUES (
                    $1, $2, $3, $4, $5, ST_SetSRID($6::geometry, 4326), $7, $8::jsonb
                )
                ON CONFLICT (id) DO UPDATE
                SET movement_type      = EXCLUDED.movement_type,
                    state              = EXCLUDED.state,
                    velocity_class     = EXCLUDED.velocity_class,
                    occurrence_date    = EXCLUDED.occurrence_date,
                    geom               = EXCLUDED.geom,
                    dataset_version_id = COALESCE(EXCLUDED.dataset_version_id,
                                                  iffi_landslides.dataset_version_id),
                    attributes         = EXCLUDED.attributes
                """,
                item.id,
                item.movement_type,
                item.state,
                item.velocity_class,
                item.occurrence_date,
                geom,
                item.dataset_version_id,
                attrs_json,
            )
    log.info("iffi.upsert_many", count=len(items_list))
    return len(items_list)


async def count_landslides() -> int:
    async with acquire() as conn:
        row = await conn.fetchrow("SELECT COUNT(*)::bigint AS n FROM iffi_landslides")
    return int(row["n"]) if row else 0


async def get_landslide(landslide_id: str) -> IFFILandslide | None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, movement_type, state, velocity_class, occurrence_date,
                   geom, dataset_version_id, attributes
            FROM iffi_landslides WHERE id = $1
            """,
            landslide_id,
        )
    if row is None:
        return None
    attrs = row["attributes"]
    if isinstance(attrs, str):
        attrs = json.loads(attrs)
    return IFFILandslide(
        id=str(row["id"]),
        movement_type=row["movement_type"],
        state=row["state"],
        velocity_class=row["velocity_class"],
        occurrence_date=row["occurrence_date"],
        geom=row["geom"],
        dataset_version_id=row["dataset_version_id"],
        attributes=attrs or {},
    )
