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

# Per-statement timeout (s) for the batch spatial aggregations. Well above
# the pool's operational default; a one-shot bootstrap over the full grid
# and the national PAI mosaic can legitimately take minutes.
_BOOTSTRAP_STMT_TIMEOUT_S = 900.0


# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------
_SEED_CELLS_SQL = """
INSERT INTO cell_static_factors (cell_id)
SELECT id FROM grid_cells WHERE aoi_id = $1
ON CONFLICT (cell_id) DO NOTHING
"""

# Count IFFI features within ~500 m of each cell. We match against the cell
# POLYGON (g.geom), not its centroid: with 1 km cells a feature near a cell
# edge sits ~700 m from the centroid and would be missed by every cell
# (centroid+500 m leaves uncovered gaps), undercounting the inventory exactly
# where real landslides cluster. We stay in EPSG:4326 and match in degrees
# ($2) so the GiST index on iffi_landslides (iffi_geom_gix) accelerates
# ST_DWithin — wrapping both sides in ST_Transform (metric) would force a full
# seq scan (O(cells x features)), which times out on real IFFI volumes.
# ~500 m ≈ 0.0045° at Italian latitudes; the density proxy saturates at 3.
_IFFI_DENSITY_SQL = """
WITH counts AS (
    SELECT g.id AS cell_id,
           COUNT(i.id)::double precision AS iffi_count
    FROM grid_cells g
    LEFT JOIN iffi_landslides i
      ON ST_DWithin(g.geom, i.geom, $2)
    WHERE g.aoi_id = $1
    GROUP BY g.id
)
UPDATE cell_static_factors c
SET iffi_density_500 = counts.iffi_count,
    updated_at = now()
FROM counts
WHERE c.cell_id = counts.cell_id
"""

# Nearest-IFFI distance per cell (metres). Uses the KNN ``<->`` operator so
# the GiST index returns the single nearest feature per cell (index scan),
# then ST_Distance over geography gives the true metric distance for just
# that one. Capped at 50 km ($2) so cells with no nearby IFFI get a finite
# value instead of NULL.
_DISTANCE_TO_IFFI_SQL = """
WITH d AS (
    SELECT g.id AS cell_id,
           LEAST(
             COALESCE(
               (SELECT ST_Distance(g.centroid::geography, i.geom::geography)
                FROM iffi_landslides i
                ORDER BY g.centroid <-> i.geom
                LIMIT 1),
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

# Rows synced into flood_hazard before migration 014 have no subdivided
# parts yet — heal them once, idempotently. Newly upserted rows are kept in
# lockstep by flood_repo.upsert_many.
_FLOOD_SUBDIV_BACKFILL_SQL = """
INSERT INTO flood_hazard_subdiv (id, hazard_class, hazard_class_norm, geom)
SELECT f.id, f.hazard_class, f.hazard_class_norm,
       ST_Subdivide(ST_CollectionExtract(ST_MakeValid(f.geom), 3), 256)
FROM flood_hazard f
WHERE NOT EXISTS (SELECT 1 FROM flood_hazard_subdiv s WHERE s.id = f.id)
"""

# Idraulica (flood): most-severe hydraulic-hazard polygon intersecting the
# cell → flood_hazard_norm + class (drives the engine's H component). NULL
# when no polygon intersects, so H stays 0 there — byte-identical baseline.
# Joins the subdivided companion, not flood_hazard: the raw mosaic has
# polygons with ~3.7M vertices whose bboxes cover thousands of cells, which
# blew the 900 s statement timeout.
_FLOOD_HAZARD_SQL = """
WITH f AS (
    SELECT g.id AS cell_id,
           MAX(fh.hazard_class_norm) AS flood_max,
           (array_agg(fh.hazard_class ORDER BY fh.hazard_class_norm DESC NULLS LAST))[1]
             AS flood_cls
    FROM grid_cells g
    LEFT JOIN flood_hazard_subdiv fh
      ON ST_Intersects(g.geom, fh.geom)
    WHERE g.aoi_id = $1
    GROUP BY g.id
)
UPDATE cell_static_factors c
SET flood_hazard_norm = f.flood_max,
    flood_hazard_class = f.flood_cls,
    updated_at = now()
FROM f
WHERE c.cell_id = f.cell_id
"""


# Distanza (m) dal centroide cella alla rete OSM più vicina, per kind.
# Il KNN ``<->`` ordina in gradi, che a ~41°N sono anisotropi (1° di
# longitudine ≈ 0.75° di latitudine in metri): il più vicino in gradi
# può non esserlo in metri, e con la banda strong a 250 m l'errore
# cambia fascia. Quindi: 10 candidati dall'indice GiST parziale (index
# scan), vincitore scelto con ST_Distance su geography. Cap a 50 km ($2).
_DISTANCE_TO_ROAD_SQL = """
WITH d AS (
    SELECT g.id AS cell_id, near.cls,
           LEAST(COALESCE(near.dist, $2::double precision), $2::double precision) AS dist
    FROM grid_cells g
    LEFT JOIN LATERAL (
        SELECT q.class AS cls,
               ST_Distance(g.centroid::geography, q.geom::geography) AS dist
        FROM (
            SELECT o.class, o.geom
            FROM osm_infrastructure o
            WHERE o.kind = 'road'
            ORDER BY g.centroid <-> o.geom
            LIMIT 10
        ) q
        ORDER BY ST_Distance(g.centroid::geography, q.geom::geography)
        LIMIT 1
    ) near ON true
    WHERE g.aoi_id = $1
)
UPDATE cell_static_factors c
SET distance_to_road_m = d.dist,
    nearest_road_class = d.cls,
    updated_at = now()
FROM d
WHERE c.cell_id = d.cell_id
"""

_DISTANCE_TO_RAIL_SQL = """
WITH d AS (
    SELECT g.id AS cell_id,
           LEAST(COALESCE(near.dist, $2::double precision), $2::double precision) AS dist
    FROM grid_cells g
    LEFT JOIN LATERAL (
        SELECT ST_Distance(g.centroid::geography, q.geom::geography) AS dist
        FROM (
            SELECT o.geom
            FROM osm_infrastructure o
            WHERE o.kind = 'rail'
            ORDER BY g.centroid <-> o.geom
            LIMIT 10
        ) q
        ORDER BY ST_Distance(g.centroid::geography, q.geom::geography)
        LIMIT 1
    ) near ON true
    WHERE g.aoi_id = $1
)
UPDATE cell_static_factors c
SET distance_to_rail_m = d.dist,
    updated_at = now()
FROM d
WHERE c.cell_id = d.cell_id
"""


# Interfaccia urbano-vegetazione (#62).
#
# Una cella è *di interfaccia* quando è urbana (CLC 1xx) e confina con una
# cella vegetata (CLC 3xx). Non "urbana" e basta: un isolato circondato da
# altri isolati non ha bosco da cui prendere fuoco, ed è la distinzione che
# separa questo termine dal `near_urban` che le frane già usano.
#
# Ogni cella riceve poi la prossimità all'interfaccia più vicina, lineare e
# azzerata oltre il raggio: 1 sull'interfaccia, 0 a `$2` metri.
_WUI_PROXIMITY_SQL = """
WITH cells AS (
    SELECT g.id, g.geom, ST_Centroid(g.geom) AS centroid, c.landuse_code
    FROM grid_cells g
    JOIN cell_static_factors c ON c.cell_id = g.id
    WHERE g.aoi_id = $1
),
interface AS (
    SELECT u.id, u.centroid
    FROM cells u
    WHERE u.landuse_code LIKE '1%'
      AND EXISTS (
          SELECT 1 FROM cells v
          WHERE v.landuse_code LIKE '3%'
            AND ST_Intersects(v.geom, u.geom)
      )
),
prox AS (
    SELECT c.id AS cell_id,
           CASE
               WHEN near.dist IS NULL THEN 0.0
               ELSE GREATEST(0.0, 1.0 - near.dist / $2)
           END AS wui
    FROM cells c
    LEFT JOIN LATERAL (
        SELECT ST_Distance(c.centroid::geography, i.centroid::geography) AS dist
        FROM interface i
        ORDER BY c.centroid <-> i.centroid
        LIMIT 1
    ) near ON near.dist <= $2
)
UPDATE cell_static_factors c
SET wui_proximity_norm = prox.wui,
    updated_at = now()
FROM prox
WHERE c.cell_id = prox.cell_id
"""

#: Oltre ~3 km dall'interfaccia il fronte non è più un problema di
#: protezione dell'abitato ma di lotta in bosco: due priorità diverse.
_WUI_RADIUS_M = 3000.0


async def compute_wui_proximity_for_aoi(aoi_id: str) -> None:
    """Fill ``wui_proximity_norm`` for one AOI.

    A clean no-op until CORINE has populated ``landuse_code``: the column
    stays NULL, which the wildfire exposure term reads as *unknown* and
    ignores — different from 0, which would mean "far from any interface".
    """
    async with acquire() as conn:
        coded = await conn.fetchval(
            """
            SELECT count(*) FROM cell_static_factors c
            JOIN grid_cells g ON g.id = c.cell_id
            WHERE g.aoi_id = $1 AND c.landuse_code IS NOT NULL
            """,
            aoi_id,
        )
        if not coded:
            log.info("static_bootstrap.wui.skip", aoi_id=aoi_id, reason="no landuse_code")
            return
        await conn.execute(
            _WUI_PROXIMITY_SQL, aoi_id, _WUI_RADIUS_M, timeout=_BOOTSTRAP_STMT_TIMEOUT_S
        )
        log.info("static_bootstrap.wui.done", aoi_id=aoi_id, cells_with_landuse=coded)


async def compute_osm_distances_for_aoi(aoi_id: str) -> None:
    """Fill distance_to_road_m / distance_to_rail_m for one AOI.

    Skips a kind entirely when osm_infrastructure has no rows for it —
    the columns stay NULL and the exposure factor degrades to the
    CORINE flags.
    """
    for kind, sql in (("road", _DISTANCE_TO_ROAD_SQL), ("rail", _DISTANCE_TO_RAIL_SQL)):
        async with acquire() as conn:
            count = await conn.fetchval(
                "SELECT count(*) FROM osm_infrastructure WHERE kind = $1", kind
            )
            if not count:
                log.info("static_bootstrap.osm_distance.skip", aoi_id=aoi_id, kind=kind)
                continue
            await conn.execute(sql, aoi_id, _DISTANCE_CAP_M, timeout=_BOOTSTRAP_STMT_TIMEOUT_S)
            log.info(
                "static_bootstrap.osm_distance.done",
                aoi_id=aoi_id,
                kind=kind,
                network_features=count,
            )


async def bootstrap_static_for_aoi(aoi_id: str) -> dict[str, int]:
    """Run the achievable static-bootstrap steps for ``aoi_id``.

    Returns counters of cells touched per stage.
    """
    aoi = await get_aoi(aoi_id)
    if aoi is None:
        raise ValueError(f"AOI not found: {aoi_id!r}")

    # GeoServer PostGIS is the authoritative source of the ISPRA landslide
    # inventory + PAI hazard. When GEOSERVER_SOURCE__DB_DSN is set, refresh
    # iffi_landslides / pai_hazard from it before the per-cell aggregation;
    # otherwise this is a clean no-op and the existing tables are used as-is.
    from limen.integrations.geoserver_source import sync_geoserver_source_for_aoi

    gs_counts = await sync_geoserver_source_for_aoi(aoi_id)
    if gs_counts["iffi"] or gs_counts["pai"] or gs_counts.get("flood"):
        log.info("static_bootstrap.geoserver_source", aoi_id=aoi_id, **gs_counts)

    # Outside the factors transaction: the backfill's work stays committed
    # even if a later aggregation times out and rolls back.
    async with acquire() as conn:
        await conn.execute(_FLOOD_SUBDIV_BACKFILL_SQL, timeout=_BOOTSTRAP_STMT_TIMEOUT_S)

    async with acquire() as conn, conn.transaction():
        result_seed = await conn.execute(_SEED_CELLS_SQL, aoi_id)
        log.info("static_bootstrap.seed_cells", aoi_id=aoi_id, result=result_seed)

        # Batch spatial aggregation over large ISPRA volumes — override the
        # pool's default per-statement timeout so these can run to completion.
        await conn.execute(
            _IFFI_DENSITY_SQL, aoi_id, _BUFFER_DEG_500M_AT_41N, timeout=_BOOTSTRAP_STMT_TIMEOUT_S
        )
        await conn.execute(
            _DISTANCE_TO_IFFI_SQL, aoi_id, _DISTANCE_CAP_M, timeout=_BOOTSTRAP_STMT_TIMEOUT_S
        )
        await conn.execute(_PAI_CLASS_SQL, aoi_id, timeout=_BOOTSTRAP_STMT_TIMEOUT_S)
        await conn.execute(_FLOOD_HAZARD_SQL, aoi_id, timeout=_BOOTSTRAP_STMT_TIMEOUT_S)

    # Distanze dalla rete OSM (strade/ferrovie) — no-op finché
    # `sync_osm_infrastructure` non ha popolato osm_infrastructure.
    await compute_osm_distances_for_aoi(aoi_id)

    # DEM derivatives — runs when LIMEN_DEM_RASTER points at a GeoTIFF
    # (e.g. TINITALY 10 m). With the env var unset the step is a clean
    # no-op + structured log; the AOI keeps progressing.
    from limen.integrations.dem import sync_dem_for_aois

    dem_written = await sync_dem_for_aois(aoi_ids=[aoi_id])
    if dem_written:
        log.info(
            "static_bootstrap.dem_done",
            aoi_id=aoi_id,
            rows_written=dem_written,
        )
    # CORINE Land Cover — runs when LIMEN_CORINE_RASTER points at a
    # categorical GeoTIFF (e.g. CLC2018 100 m mosaic).
    from limen.integrations.corine import sync_corine_for_aois

    corine_written = await sync_corine_for_aois(aoi_ids=[aoi_id])
    if corine_written:
        log.info(
            "static_bootstrap.corine_done",
            aoi_id=aoi_id,
            rows_written=corine_written,
        )

    # Dopo CORINE, perché legge `landuse_code`: invertirli lascerebbe la
    # colonna WUI ferma di un giro rispetto alla copertura del suolo.
    await compute_wui_proximity_for_aoi(aoi_id)

    # ISPRA Carta Geologica — vector shapefile + faults; runs when
    # LIMEN_GEOLOGICAL_SHAPEFILE points at a polygon file.
    from limen.integrations.geological import sync_geological_for_aois

    geo_written = await sync_geological_for_aois(aoi_ids=[aoi_id])
    if geo_written:
        log.info(
            "static_bootstrap.geological_done",
            aoi_id=aoi_id,
            rows_written=geo_written,
        )

    total = await count_factors()
    log.info("static_bootstrap.done", aoi_id=aoi_id, factor_rows=total)
    return {"cells_with_factors": total}
