"""PAI hazard polygons repository (Piano di Assetto Idrogeologico)."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.validation import make_valid

from limen.core.logging import get_logger
from limen.data.db import acquire

log = get_logger(__name__)

# Map PAI hazard classes to a 0..1 normalised score used by the scoring engine.
# AA = "Area di Attenzione" (lowest); P1..P4 = increasing hazard.
PAI_CLASS_TO_NORM: dict[str, float] = {
    "AA": 0.20,
    "P1": 0.40,
    "P2": 0.60,
    "P3": 0.80,
    "P4": 1.00,
}


@dataclass(frozen=True, slots=True)
class PAIHazard:
    id: str
    hazard_class: str
    authority: str | None
    geom: MultiPolygon
    dataset_version_id: int | None = None
    attributes: dict[str, Any] | None = None

    @property
    def hazard_class_norm(self) -> float | None:
        return PAI_CLASS_TO_NORM.get(self.hazard_class.upper().strip())


def _as_multipolygon(geom: BaseGeometry) -> MultiPolygon | None:
    if isinstance(geom, MultiPolygon):
        return geom
    if isinstance(geom, Polygon):
        return MultiPolygon([geom])
    fixed = make_valid(geom)
    if isinstance(fixed, MultiPolygon):
        return fixed
    if isinstance(fixed, Polygon):
        return MultiPolygon([fixed])
    return None


async def upsert_many(items: Iterable[PAIHazard]) -> int:
    """Insert-or-update PAI hazard polygons in a single transaction."""
    items_list = list(items)
    if not items_list:
        return 0
    async with acquire() as conn, conn.transaction():
        for item in items_list:
            multi = _as_multipolygon(item.geom)
            if multi is None:
                log.warning("pai.skip", reason="non-polygon geometry", pai_id=item.id)
                continue
            attrs_json = json.dumps(item.attributes or {}, default=str)
            await conn.execute(
                """
                INSERT INTO pai_hazard (
                    id, hazard_class, authority, geom, hazard_class_norm,
                    dataset_version_id, attributes
                ) VALUES (
                    $1, $2, $3, ST_SetSRID($4::geometry, 4326), $5, $6, $7::jsonb
                )
                ON CONFLICT (id) DO UPDATE
                SET hazard_class       = EXCLUDED.hazard_class,
                    authority          = EXCLUDED.authority,
                    geom               = EXCLUDED.geom,
                    hazard_class_norm  = EXCLUDED.hazard_class_norm,
                    dataset_version_id = COALESCE(EXCLUDED.dataset_version_id,
                                                  pai_hazard.dataset_version_id),
                    attributes         = EXCLUDED.attributes
                """,
                item.id,
                item.hazard_class,
                item.authority,
                multi,
                item.hazard_class_norm,
                item.dataset_version_id,
                attrs_json,
            )
    log.info("pai.upsert_many", count=len(items_list))
    return len(items_list)


async def count_pai() -> int:
    async with acquire() as conn:
        row = await conn.fetchrow("SELECT COUNT(*)::bigint AS n FROM pai_hazard")
    return int(row["n"]) if row else 0
