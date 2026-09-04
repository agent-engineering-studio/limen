-- Deterministic feature order in the risk_at() tiles (issue #82 follow-up).
--
-- ST_AsMVT serialises features in the order the aggregate receives them, and
-- that order came straight from the physical scan. Rebuilding the table in
-- migration 028 reshuffled the heap, so the same tile came back with the same
-- 60k features in a different order and therefore different bytes: content
-- identical, checksum different. Any VACUUM FULL or partition boundary would
-- have done the same.
--
-- Sorting by cell_id inside the aggregate makes a tile's bytes a function of
-- its content alone, which is what an ETag or a proxy cache needs. The sort
-- is cheap next to ST_AsMVTGeom over the same rows.
CREATE OR REPLACE FUNCTION public.risk_at(
    z integer, x integer, y integer,
    hours_ago integer DEFAULT 0,
    p_hazard hazard_type DEFAULT 'landslide'
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
    WHERE ra.hazard_type = p_hazard
      AND ra.computed_at <= now() - make_interval(hours => GREATEST(hours_ago, 0))
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
SELECT ST_AsMVT(mvt.*, 'public.v_risk_tiles', 4096, 'geom' ORDER BY mvt.cell_id)
FROM mvt;
$$ LANGUAGE sql STABLE PARALLEL SAFE;

COMMENT ON FUNCTION public.risk_at IS
'Vector tiles dello stato di rischio per cella a N ore fa (timeline), per hazard. Ordine feature deterministico.';
