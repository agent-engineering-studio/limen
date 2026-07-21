-- Administrative comune boundaries (ISTAT) + cell→comune tag + comune rollup.
-- Boundaries are imported into the operational DB by `limen seed-comuni` so
-- nothing queries the GeoServer DB in the hot path. mv_comune_risk mirrors
-- v_region_tiles (migration 019) one level down: worst-cell class + counts.

CREATE TABLE IF NOT EXISTS comuni (
    istat_code text PRIMARY KEY,
    name       text NOT NULL,
    aoi_id     text NOT NULL REFERENCES aoi(id) ON DELETE CASCADE,
    geom       geometry(MultiPolygon, 4326) NOT NULL,
    centroid   geometry(Point, 4326) GENERATED ALWAYS AS (ST_PointOnSurface(geom)) STORED
);
CREATE INDEX IF NOT EXISTS comuni_geom_gix ON comuni USING GIST (geom);
CREATE INDEX IF NOT EXISTS comuni_aoi_idx  ON comuni (aoi_id);

CREATE TABLE IF NOT EXISTS cell_comune (
    cell_id    text PRIMARY KEY REFERENCES grid_cells (id) ON DELETE CASCADE,
    istat_code text NOT NULL REFERENCES comuni (istat_code) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS cell_comune_istat_idx ON cell_comune (istat_code);

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_comune_risk AS
SELECT
    c.istat_code,
    c.name,
    c.aoi_id,
    COUNT(m.cell_id)                                            AS n_cells,
    COUNT(*) FILTER (WHERE m.risk_level = 'None')               AS n_none,
    COUNT(*) FILTER (WHERE m.risk_level = 'Low')                AS n_low,
    COUNT(*) FILTER (WHERE m.risk_level = 'Moderate')           AS n_moderate,
    COUNT(*) FILTER (WHERE m.risk_level = 'High')               AS n_high,
    COUNT(*) FILTER (WHERE m.risk_level = 'VeryHigh')           AS n_veryhigh,
    COUNT(*) FILTER (WHERE m.risk_level IN ('High','VeryHigh')) AS n_alert,
    MAX(m.risk_score)                                           AS max_score,
    COALESCE(
        (array_agg(m.risk_level ORDER BY m.risk_score DESC NULLS LAST))[1],
        'None'
    )                                                           AS worst_class,
    COALESCE(SUM((m.factors->>'e')::double precision)
             FILTER (WHERE m.risk_level IN ('High','VeryHigh')), 0) AS exposure_rank,
    c.geom,
    c.centroid
FROM comuni c
LEFT JOIN cell_comune cc ON cc.istat_code = c.istat_code
LEFT JOIN mv_latest_risk m ON m.cell_id = cc.cell_id AND m.risk_score IS NOT NULL
GROUP BY c.istat_code, c.name, c.aoi_id, c.geom, c.centroid
WITH NO DATA;

CREATE UNIQUE INDEX IF NOT EXISTS mv_comune_risk_pk   ON mv_comune_risk (istat_code);
CREATE INDEX IF NOT EXISTS mv_comune_risk_geom_gix    ON mv_comune_risk USING GIST (geom);
CREATE INDEX IF NOT EXISTS mv_comune_risk_aoi_idx     ON mv_comune_risk (aoi_id);

-- Comune refresh helper (mirrors refresh_mv_latest_risk semantics).
CREATE OR REPLACE FUNCTION refresh_mv_comune_risk() RETURNS integer
LANGUAGE plpgsql AS $$
BEGIN
    BEGIN
        REFRESH MATERIALIZED VIEW CONCURRENTLY mv_comune_risk;
        RETURN 1;
    EXCEPTION
        WHEN feature_not_supported THEN
            REFRESH MATERIALIZED VIEW mv_comune_risk;
            RETURN 0;
        WHEN OTHERS THEN
            RAISE NOTICE 'refresh_mv_comune_risk failed: %', SQLERRM;
            RETURN -1;
    END;
END $$;

-- Chain comune refresh onto the single supported latest-refresh path so every
-- existing caller (PersistResult) updates the comune rollup for free. Redefine
-- (never edit migration 007) — refresh latest first, then comune.
CREATE OR REPLACE FUNCTION refresh_mv_latest_risk() RETURNS integer
LANGUAGE plpgsql AS $$
DECLARE latest_rc integer;
BEGIN
    BEGIN
        REFRESH MATERIALIZED VIEW CONCURRENTLY mv_latest_risk;
        latest_rc := 1;
    EXCEPTION
        WHEN feature_not_supported THEN
            REFRESH MATERIALIZED VIEW mv_latest_risk;
            latest_rc := 0;
        WHEN OTHERS THEN
            RAISE NOTICE 'refresh_mv_latest_risk failed: %', SQLERRM;
            RETURN -1;
    END;
    -- Comune depends on the freshly refreshed latest view. Best-effort:
    -- a comune-refresh failure must not mask a successful latest refresh.
    PERFORM refresh_mv_comune_risk();
    RETURN latest_rc;
END $$;
