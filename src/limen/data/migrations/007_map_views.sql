-- 007_map_views.sql
--
-- Materialized view consumed by pg_tileserv to render the public map.
-- One row per grid cell with the *latest* persisted assessment for that
-- cell (NULL on cells that have never been scored).
--
-- The UNIQUE index on cell_id is what makes
--   REFRESH MATERIALIZED VIEW CONCURRENTLY mv_latest_risk;
-- possible — without it, every refresh would block readers (and break
-- the map for a few seconds on every monitoring tick).
--
-- ``refresh_mv_latest_risk()`` is the single supported refresh path:
-- callers (the workflow's PersistResult executor + ad-hoc operators)
-- invoke it instead of issuing the REFRESH statement directly. The
-- function falls back to a non-concurrent refresh the first time around
-- (CONCURRENTLY requires the matview to have been populated at least
-- once).

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_latest_risk AS
WITH ranked AS (
    SELECT ra.*,
           ROW_NUMBER() OVER (PARTITION BY ra.cell_id ORDER BY ra.computed_at DESC) AS rn
    FROM risk_assessments ra
)
SELECT g.id            AS cell_id,
       g.aoi_id        AS aoi_id,
       g.geom          AS geom,
       g.centroid      AS centroid,
       g.area_km2      AS area_km2,
       r.score         AS risk_score,
       r.class         AS risk_level,
       r.horizon       AS horizon,
       r.pipeline_version AS pipeline_version,
       r.computed_at   AS computed_at,
       r.factors       AS factors,
       r.explanation   AS explanation
FROM grid_cells g
LEFT JOIN ranked r ON r.cell_id = g.id AND r.rn = 1
WITH NO DATA;

CREATE UNIQUE INDEX IF NOT EXISTS mv_latest_risk_cell_idx
    ON mv_latest_risk (cell_id);
CREATE INDEX IF NOT EXISTS mv_latest_risk_aoi_idx
    ON mv_latest_risk (aoi_id);
CREATE INDEX IF NOT EXISTS mv_latest_risk_geom_gix
    ON mv_latest_risk USING GIST (geom);
CREATE INDEX IF NOT EXISTS mv_latest_risk_level_idx
    ON mv_latest_risk (risk_level);

-- Populate immediately so pg_tileserv has rows to serve before the first
-- monitoring cycle finishes.
REFRESH MATERIALIZED VIEW mv_latest_risk;


-- ---------------------------------------------------------------------------
-- Refresh helper.
-- ---------------------------------------------------------------------------
-- Tries CONCURRENTLY first; falls back to a blocking refresh if the matview
-- has never been populated (Postgres requires a prior plain REFRESH for
-- CONCURRENTLY to work). Returns 1 on concurrent, 0 on blocking, -1 on
-- error so callers can log without raising.
CREATE OR REPLACE FUNCTION refresh_mv_latest_risk() RETURNS integer
LANGUAGE plpgsql
AS $$
BEGIN
    BEGIN
        REFRESH MATERIALIZED VIEW CONCURRENTLY mv_latest_risk;
        RETURN 1;
    EXCEPTION
        WHEN feature_not_supported THEN
            -- Triggered on the first call before any non-concurrent refresh.
            REFRESH MATERIALIZED VIEW mv_latest_risk;
            RETURN 0;
        WHEN OTHERS THEN
            RAISE NOTICE 'refresh_mv_latest_risk failed: %', SQLERRM;
            RETURN -1;
    END;
END
$$;
