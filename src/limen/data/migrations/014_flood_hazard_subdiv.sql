-- 014_flood_hazard_subdiv.sql
--
-- Query-side companion of `flood_hazard`. The ISPRA idraulica mosaic
-- contains polygons with millions of vertices (max observed ~3.7M) whose
-- bounding boxes span thousands of grid cells, so the per-cell
-- ST_Intersects aggregation in bootstrap-static blows past its statement
-- timeout. Each source polygon is stored here split by ST_Subdivide into
-- small parts, keeping the GiST index selective and the exact intersection
-- tests cheap. `flood_repo.upsert_many` keeps this table in lockstep with
-- `flood_hazard`; bootstrap-static backfills rows synced before this table
-- existed. `flood_hazard` remains the authoritative store.

CREATE TABLE IF NOT EXISTS flood_hazard_subdiv (
    id                 text NOT NULL,
    hazard_class       text NOT NULL,
    hazard_class_norm  double precision,
    geom               geometry(Polygon, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS flood_hazard_subdiv_geom_gix
    ON flood_hazard_subdiv USING GIST (geom);
CREATE INDEX IF NOT EXISTS flood_hazard_subdiv_id_ix
    ON flood_hazard_subdiv (id);
