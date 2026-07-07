-- Time-travel vector tiles: the timeline slider was a V1 stub because
-- mv_latest_risk only holds the latest snapshot. pg_tileserv publishes
-- this function as /public.risk_at/{z}/{x}/{y}.pbf?hours_ago=N — the
-- per-cell state as of N hours ago, straight from risk_assessments
-- (bounded by the 14-day retention). The MVT layer is named like the
-- static view so the frontend swaps the tile URL without touching the
-- style layers.

CREATE OR REPLACE FUNCTION public.risk_at(
    z integer, x integer, y integer,
    hours_ago integer DEFAULT 0
) RETURNS bytea AS $$
WITH bounds AS (
    SELECT ST_TileEnvelope(z, x, y) AS b
),
cells AS (
    SELECT g.id, g.geom
    FROM grid_cells g, bounds
    WHERE ST_Transform(g.geom, 3857) && bounds.b
),
latest AS (
    SELECT DISTINCT ON (ra.cell_id) ra.cell_id, ra.score, ra.class
    FROM risk_assessments ra
    JOIN cells c ON c.id = ra.cell_id
    WHERE ra.computed_at <= now() - make_interval(hours => GREATEST(hours_ago, 0))
    ORDER BY ra.cell_id, ra.computed_at DESC
),
mvt AS (
    SELECT ST_AsMVTGeom(ST_Transform(c.geom, 3857), bounds.b) AS geom,
           c.id      AS cell_id,
           l.score   AS risk_score,
           l.class   AS risk_level
    FROM cells c
    JOIN latest l ON l.cell_id = c.id, bounds
)
SELECT ST_AsMVT(mvt.*, 'public.v_risk_tiles', 4096, 'geom') FROM mvt;
$$ LANGUAGE sql STABLE PARALLEL SAFE;

COMMENT ON FUNCTION public.risk_at IS
'Vector tiles dello stato di rischio per cella a N ore fa (timeline).';
