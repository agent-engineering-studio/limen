-- 013_flood_hazard.sql
--
-- Operational store for the ISPRA hydraulic-hazard (idraulica) mosaic, the
-- source of the deterministic engine's `H` component. Mirrors `pai_hazard`:
-- the geoserver_source loader copies the idraulica polygons here from the
-- GeoServer PostGIS, and `bootstrap-static` aggregates them per cell into
-- `cell_static_factors.flood_hazard_class/norm` (migration 011).
--
-- The idraulica classes map onto the shared AA/P1..P4 ladder: elevata → P3,
-- media → P2, bassa → P1 (see limen.data.repos.pai_repo.PAI_CLASS_TO_NORM).

CREATE TABLE IF NOT EXISTS flood_hazard (
    id                 text PRIMARY KEY,
    hazard_class       text NOT NULL,
    hazard_class_norm  double precision,
    geom               geometry(MultiPolygon, 4326) NOT NULL,
    attributes         jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS flood_hazard_geom_gix ON flood_hazard USING GIST (geom);
