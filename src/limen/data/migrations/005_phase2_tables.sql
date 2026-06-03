-- 005_phase2_tables.sql
--
-- Phase 2 tables and column extensions for external integrations:
--   * seismic_events     — INGV FDSN events + optional ShakeMap raster ref
--   * fire_perimeters    — EFFIS burnt-area perimeters (+ optional dNBR raster ref)
--   * cell_static_factors columns added by the static-bootstrap pipeline
--   * pai_hazard.normalised hazard class column (0..1) for the scoring engine
--
-- All new tables follow the conventions of 002_core_tables.sql:
-- EPSG:4326, GiST on geometry, dataset_version_id when applicable.

-- ---------------------------------------------------------------------------
-- INGV: seismic events + ShakeMap raster reference
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS seismic_events (
    id                  text PRIMARY KEY,                    -- INGV eventID
    origin_time         timestamptz NOT NULL,
    magnitude           double precision NOT NULL,
    magnitude_type      text,
    depth_km            double precision,
    geom                geometry(Point, 4326) NOT NULL,
    region              text,
    shakemap_path       text,                                -- ObjectStore key, NULL if absent
    raster_ref_id       bigint REFERENCES raster_refs(id) ON DELETE SET NULL,
    dataset_version_id  bigint REFERENCES dataset_versions(id) ON DELETE SET NULL,
    attributes          jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS seismic_events_geom_gix      ON seismic_events USING GIST (geom);
CREATE INDEX IF NOT EXISTS seismic_events_time_idx      ON seismic_events (origin_time DESC);
CREATE INDEX IF NOT EXISTS seismic_events_magnitude_idx ON seismic_events (magnitude DESC);

-- ---------------------------------------------------------------------------
-- EFFIS: burnt-area perimeters
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fire_perimeters (
    id                  text PRIMARY KEY,                    -- EFFIS feature id
    fire_date           date,
    area_ha             double precision,
    country             text,
    province            text,
    geom                geometry(MultiPolygon, 4326) NOT NULL,
    dnbr_path           text,                                -- ObjectStore key for dNBR, NULL if absent
    raster_ref_id       bigint REFERENCES raster_refs(id) ON DELETE SET NULL,
    dataset_version_id  bigint REFERENCES dataset_versions(id) ON DELETE SET NULL,
    attributes          jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS fire_perimeters_geom_gix ON fire_perimeters USING GIST (geom);
CREATE INDEX IF NOT EXISTS fire_perimeters_date_idx ON fire_perimeters (fire_date DESC);

-- ---------------------------------------------------------------------------
-- cell_static_factors: columns the static-bootstrap pipeline writes
-- ---------------------------------------------------------------------------
ALTER TABLE cell_static_factors ADD COLUMN IF NOT EXISTS landuse_code      text;
ALTER TABLE cell_static_factors ADD COLUMN IF NOT EXISTS litho_weight      double precision;
ALTER TABLE cell_static_factors ADD COLUMN IF NOT EXISTS dist_faults_m     double precision;
ALTER TABLE cell_static_factors ADD COLUMN IF NOT EXISTS iffi_density_500  double precision;
ALTER TABLE cell_static_factors ADD COLUMN IF NOT EXISTS pai_class_norm    double precision
    CHECK (pai_class_norm IS NULL OR (pai_class_norm >= 0 AND pai_class_norm <= 1));
ALTER TABLE cell_static_factors ADD COLUMN IF NOT EXISTS curvature         double precision;

-- ---------------------------------------------------------------------------
-- pai_hazard: normalised hazard class (0..1). Mapping AA/P1..P4 → numeric
-- happens at ingest time in integrations/idrogeo/parsers.py.
-- ---------------------------------------------------------------------------
ALTER TABLE pai_hazard ADD COLUMN IF NOT EXISTS hazard_class_norm double precision
    CHECK (hazard_class_norm IS NULL OR (hazard_class_norm >= 0 AND hazard_class_norm <= 1));
