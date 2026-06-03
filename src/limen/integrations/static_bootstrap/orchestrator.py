"""Static-bootstrap orchestrator.

All computations that can be done in pure PostGIS run as a few set-based
SQL statements: vastly faster than per-cell loops in Python.

Heavy raster/vector ingest (DEM derivatives, CORINE, lithology) are
intentionally left as no-op log lines so the pipeline finishes cleanly
even when those datasets are not yet wired up.
"""

from __future__ import annotations

from limen.core.logging import get_logger
from limen.data.db import acquire
from limen.data.repos.aoi_repo import get_aoi
from limen.data.repos.cell_static_factors_repo import count_factors

log = get_logger(__name__)

# 500 m buffer in metres → degrees varies with latitude; for the Puglia /
# Basilicata pilot we use a constant approximation good to ~10 % at
# 41° N. The proper way is to reproject to EPSG:3035 — left as a later
# optimisation when the DEM pipeline lands and the metric CRS path is
# already established.
_BUFFER_DEG_500M_AT_41N = 500.0 / 111_320.0  # ≈ 0.00449

# Maximum distance (m) we consider for distance_to_iffi_m; further than
# this the cell is "not near any landslide" and we record this cap.
_DISTANCE_CAP_M = 50_000.0


# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------
_SEED_CELLS_SQL = """
INSERT INTO cell_static_factors (cell_id)
SELECT id FROM grid_cells WHERE aoi_id = $1
ON CONFLICT (cell_id) DO NOTHING
"""

# Count IFFI features within a 500 m buffer around each cell's centroid.
# We project both sides to EPSG:3035 (metric) for the buffer + distance
# calculations — gives "actual" 500 m everywhere on the Italian
# peninsula.
_IFFI_DENSITY_SQL = """
WITH counts AS (
    SELECT g.id AS cell_id,
           COUNT(i.id)::double precision AS iffi_count
    FROM grid_cells g
    LEFT JOIN iffi_landslides i
      ON ST_DWithin(
           ST_Transform(g.centroid, 3035),
           ST_Transform(i.geom,     3035),
           500.0
         )
    WHERE g.aoi_id = $1
    GROUP BY g.id
)
UPDATE cell_static_factors c
SET iffi_density_500 = counts.iffi_count,
    updated_at = now()
FROM counts
WHERE c.cell_id = counts.cell_id
"""

# Nearest-IFFI distance per cell (metric, projected). Capped at 50 km so
# AOIs without any IFFI within reasonable range get a finite value
# instead of NULL.
_DISTANCE_TO_IFFI_SQL = """
WITH d AS (
    SELECT g.id AS cell_id,
           LEAST(
             COALESCE(
               (SELECT MIN(
                  ST_Distance(
                    ST_Transform(g.centroid, 3035),
                    ST_Transform(i.geom,     3035)
                  )
                )
                FROM iffi_landslides i),
               $2::double precision
             ),
             $2::double precision
           ) AS dist
    FROM grid_cells g
    WHERE g.aoi_id = $1
)
UPDATE cell_static_factors c
SET distance_to_iffi_m = d.dist,
    updated_at = now()
FROM d
WHERE c.cell_id = d.cell_id
"""

# PAI: take the maximum normalised hazard class of any PAI polygon
# intersecting the cell. NULL if no polygon intersects.
_PAI_CLASS_SQL = """
WITH p AS (
    SELECT g.id AS cell_id,
           MAX(pai.hazard_class_norm) AS pai_max
    FROM grid_cells g
    LEFT JOIN pai_hazard pai
      ON ST_Intersects(g.geom, pai.geom)
    WHERE g.aoi_id = $1
    GROUP BY g.id
)
UPDATE cell_static_factors c
SET pai_class_norm = p.pai_max,
    updated_at = now()
FROM p
WHERE c.cell_id = p.cell_id
"""


async def bootstrap_static_for_aoi(aoi_id: str) -> dict[str, int]:
    """Run the achievable static-bootstrap steps for ``aoi_id``.

    Returns counters of cells touched per stage.
    """
    aoi = await get_aoi(aoi_id)
    if aoi is None:
        raise ValueError(f"AOI not found: {aoi_id!r}")

    async with acquire() as conn, conn.transaction():
        result_seed = await conn.execute(_SEED_CELLS_SQL, aoi_id)
        log.info("static_bootstrap.seed_cells", aoi_id=aoi_id, result=result_seed)

        await conn.execute(_IFFI_DENSITY_SQL, aoi_id)
        await conn.execute(_DISTANCE_TO_IFFI_SQL, aoi_id, _DISTANCE_CAP_M)
        await conn.execute(_PAI_CLASS_SQL, aoi_id)

    # TODO(Phase 3): DEM derivatives (slope / aspect / curvature / TWI / elevation)
    # via TINITALY 10 m tiles → ObjectStore COG → rasterio zonal stats.
    log.warning(
        "static_bootstrap.skip",
        aoi_id=aoi_id,
        component="dem_derivatives",
        note="DEM tiles + zonal stats not yet implemented; slope/aspect/twi remain NULL",
    )
    # TODO(Phase 3): CORINE dominant land cover per cell.
    log.warning(
        "static_bootstrap.skip",
        aoi_id=aoi_id,
        component="corine_landuse",
        note="CORINE ingest pending; landuse_code remains NULL",
    )
    # TODO(Phase 3): ISPRA Carta Geologica vettoriale → lithology + dist_faults.
    log.warning(
        "static_bootstrap.skip",
        aoi_id=aoi_id,
        component="lithology",
        note=(
            "ISPRA geological map ingest pending; "
            "lithology/litho_weight/dist_faults_m remain NULL"
        ),
    )

    total = await count_factors()
    log.info("static_bootstrap.done", aoi_id=aoi_id, factor_rows=total)
    return {"cells_with_factors": total}
