"""Per-cell static factors repository.

The static-bootstrap pipeline writes rows here. Every column is nullable
on purpose: when a source dataset is unavailable, the bootstrap skips
that field rather than crashing.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from limen.core.logging import get_logger
from limen.data.db import acquire

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CellStaticFactors:
    cell_id: str
    slope_deg: float | None = None
    aspect_deg: float | None = None
    elevation_m: float | None = None
    twi: float | None = None
    curvature: float | None = None
    lithology: str | None = None
    land_cover: str | None = None
    landuse_code: str | None = None
    litho_weight: float | None = None
    dist_faults_m: float | None = None
    distance_to_iffi_m: float | None = None
    iffi_density_500: float | None = None
    pai_class_norm: float | None = None
    # Phase 12+: flood hazard from the ISPRA Mosaicatura Idraulica.
    flood_hazard_class: str | None = None
    flood_hazard_norm: float | None = None
    extras: dict[str, Any] | None = None


async def upsert_many(items: Iterable[CellStaticFactors]) -> int:
    """Bulk upsert (single transaction). Returns the count written."""
    items_list = list(items)
    if not items_list:
        return 0
    async with acquire() as conn, conn.transaction():
        for it in items_list:
            extras_json = json.dumps(it.extras or {}, default=str)
            await conn.execute(
                """
                INSERT INTO cell_static_factors (
                    cell_id, slope_deg, aspect_deg, elevation_m, twi, curvature,
                    lithology, land_cover, landuse_code, litho_weight,
                    dist_faults_m, distance_to_iffi_m, iffi_density_500,
                    pai_class_norm, flood_hazard_class, flood_hazard_norm, extras
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
                    $14, $15, $16, $17::jsonb
                )
                ON CONFLICT (cell_id) DO UPDATE
                SET slope_deg    = COALESCE(EXCLUDED.slope_deg,
                                            cell_static_factors.slope_deg),
                    aspect_deg   = COALESCE(EXCLUDED.aspect_deg,
                                            cell_static_factors.aspect_deg),
                    elevation_m  = COALESCE(EXCLUDED.elevation_m,
                                            cell_static_factors.elevation_m),
                    twi          = COALESCE(EXCLUDED.twi,
                                            cell_static_factors.twi),
                    curvature    = COALESCE(EXCLUDED.curvature,
                                            cell_static_factors.curvature),
                    lithology    = COALESCE(EXCLUDED.lithology,
                                            cell_static_factors.lithology),
                    land_cover   = COALESCE(EXCLUDED.land_cover,
                                            cell_static_factors.land_cover),
                    landuse_code = COALESCE(EXCLUDED.landuse_code,
                                            cell_static_factors.landuse_code),
                    litho_weight = COALESCE(EXCLUDED.litho_weight,
                                            cell_static_factors.litho_weight),
                    dist_faults_m = COALESCE(EXCLUDED.dist_faults_m,
                                             cell_static_factors.dist_faults_m),
                    distance_to_iffi_m = COALESCE(EXCLUDED.distance_to_iffi_m,
                                                  cell_static_factors.distance_to_iffi_m),
                    iffi_density_500 = COALESCE(EXCLUDED.iffi_density_500,
                                                cell_static_factors.iffi_density_500),
                    pai_class_norm = COALESCE(EXCLUDED.pai_class_norm,
                                              cell_static_factors.pai_class_norm),
                    flood_hazard_class = COALESCE(EXCLUDED.flood_hazard_class,
                                                  cell_static_factors.flood_hazard_class),
                    flood_hazard_norm  = COALESCE(EXCLUDED.flood_hazard_norm,
                                                  cell_static_factors.flood_hazard_norm),
                    extras       = cell_static_factors.extras || EXCLUDED.extras,
                    updated_at   = now()
                """,
                it.cell_id,
                it.slope_deg,
                it.aspect_deg,
                it.elevation_m,
                it.twi,
                it.curvature,
                it.lithology,
                it.land_cover,
                it.landuse_code,
                it.litho_weight,
                it.dist_faults_m,
                it.distance_to_iffi_m,
                it.iffi_density_500,
                it.pai_class_norm,
                it.flood_hazard_class,
                it.flood_hazard_norm,
                extras_json,
            )
    log.info("cell_static_factors.upsert_many", count=len(items_list))
    return len(items_list)


async def count_factors() -> int:
    async with acquire() as conn:
        row = await conn.fetchrow("SELECT COUNT(*)::bigint AS n FROM cell_static_factors")
    return int(row["n"]) if row else 0


async def get_for_cell(cell_id: str) -> CellStaticFactors | None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT cell_id, slope_deg, aspect_deg, elevation_m, twi, curvature,
                   lithology, land_cover, landuse_code, litho_weight,
                   dist_faults_m, distance_to_iffi_m, iffi_density_500,
                   pai_class_norm, flood_hazard_class, flood_hazard_norm, extras
            FROM cell_static_factors WHERE cell_id = $1
            """,
            cell_id,
        )
    if row is None:
        return None
    extras = row["extras"]
    if isinstance(extras, str):
        extras = json.loads(extras)
    return CellStaticFactors(
        cell_id=row["cell_id"],
        slope_deg=row["slope_deg"],
        aspect_deg=row["aspect_deg"],
        elevation_m=row["elevation_m"],
        twi=row["twi"],
        curvature=row["curvature"],
        lithology=row["lithology"],
        land_cover=row["land_cover"],
        landuse_code=row["landuse_code"],
        litho_weight=row["litho_weight"],
        dist_faults_m=row["dist_faults_m"],
        distance_to_iffi_m=row["distance_to_iffi_m"],
        iffi_density_500=row["iffi_density_500"],
        pai_class_norm=row["pai_class_norm"],
        flood_hazard_class=row["flood_hazard_class"],
        flood_hazard_norm=row["flood_hazard_norm"],
        extras=extras or {},
    )
