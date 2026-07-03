"""Hydraulic-hazard (idraulica) polygons repository.

Mirrors :mod:`limen.data.repos.pai_repo` for the ISPRA idraulica mosaic: the
same AA/P1..P4 → norm ladder, `MultiPolygon`, idempotent upsert by id. Feeds
the deterministic engine's `H` component via the per-cell aggregation in
`bootstrap-static`.
"""

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
from limen.data.repos.pai_repo import PAI_CLASS_TO_NORM

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class FloodHazard:
    id: str
    hazard_class: str
    geom: MultiPolygon
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


async def upsert_many(items: Iterable[FloodHazard]) -> int:
    """Insert-or-update hydraulic-hazard polygons in a single transaction."""
    items_list = list(items)
    if not items_list:
        return 0
    async with acquire() as conn, conn.transaction():
        for item in items_list:
            multi = _as_multipolygon(item.geom)
            if multi is None:
                log.warning("flood.skip", reason="non-polygon geometry", flood_id=item.id)
                continue
            attrs_json = json.dumps(item.attributes or {}, default=str)
            await conn.execute(
                """
                INSERT INTO flood_hazard (
                    id, hazard_class, hazard_class_norm, geom, attributes
                ) VALUES (
                    $1, $2, $3, ST_SetSRID($4::geometry, 4326), $5::jsonb
                )
                ON CONFLICT (id) DO UPDATE
                SET hazard_class      = EXCLUDED.hazard_class,
                    hazard_class_norm = EXCLUDED.hazard_class_norm,
                    geom              = EXCLUDED.geom,
                    attributes        = EXCLUDED.attributes
                """,
                item.id,
                item.hazard_class,
                item.hazard_class_norm,
                multi,
                attrs_json,
            )
            # Keep the subdivided companion (migration 014) in lockstep, in
            # the same transaction — the per-cell aggregation joins it
            # instead of the raw multi-million-vertex mosaic polygons.
            await conn.execute("DELETE FROM flood_hazard_subdiv WHERE id = $1", item.id)
            await conn.execute(
                """
                INSERT INTO flood_hazard_subdiv (id, hazard_class, hazard_class_norm, geom)
                SELECT id, hazard_class, hazard_class_norm,
                       ST_Subdivide(ST_CollectionExtract(ST_MakeValid(geom), 3), 256)
                FROM flood_hazard
                WHERE id = $1
                """,
                item.id,
            )
    log.info("flood.upsert_many", count=len(items_list))
    return len(items_list)
