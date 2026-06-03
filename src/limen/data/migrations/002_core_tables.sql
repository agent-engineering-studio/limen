-- 002_core_tables.sql
--
-- Core domain tables for Limen, following project doc §3.3.3.
-- All geometries are stored in EPSG:4326 (WGS84); reprojection to projected
-- metric CRS happens in application code when distances/areas are needed.

-- Dataset versions: a single registry of every external dataset ingested
-- (IFFI, PAI, ECMWF reanalyses, etc.). Other tables reference this so we
-- can answer "which version of dataset X did risk assessment Y use?".
CREATE TABLE IF NOT EXISTS dataset_versions (
    id              bigserial PRIMARY KEY,
    source          text        NOT NULL,
    dataset         text        NOT NULL,
    version         text        NOT NULL,
    fetched_at      timestamptz NOT NULL DEFAULT now(),
    valid_from      timestamptz,
    valid_to        timestamptz,
    metadata        jsonb       NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (source, dataset, version)
);

-- Area of Interest: the geographic boundary of a region under analysis
-- (e.g. Puglia, Basilicata, a municipality, a project polygon).
CREATE TABLE IF NOT EXISTS aoi (
    id              text PRIMARY KEY,
    name            text        NOT NULL,
    kind            text        NOT NULL DEFAULT 'region',
    geom            geometry(MultiPolygon, 4326) NOT NULL,
    bbox            geometry(Polygon, 4326)      GENERATED ALWAYS AS (ST_Envelope(geom)) STORED,
    metadata        jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS aoi_geom_gix ON aoi USING GIST (geom);
CREATE INDEX IF NOT EXISTS aoi_bbox_gix ON aoi USING GIST (bbox);

-- Discretisation grid: nominally 1 km² cells clipped to an AOI. Deterministic
-- composite id (`aoi_id|row|col`) keeps cell stability across re-seeds.
CREATE TABLE IF NOT EXISTS grid_cells (
    id              text PRIMARY KEY,
    aoi_id          text        NOT NULL REFERENCES aoi(id) ON DELETE CASCADE,
    row_idx         integer     NOT NULL,
    col_idx         integer     NOT NULL,
    geom            geometry(Polygon, 4326) NOT NULL,
    centroid        geometry(Point, 4326)   GENERATED ALWAYS AS (ST_Centroid(geom)) STORED,
    area_km2        double precision        NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (aoi_id, row_idx, col_idx)
);
CREATE INDEX IF NOT EXISTS grid_cells_geom_gix     ON grid_cells USING GIST (geom);
CREATE INDEX IF NOT EXISTS grid_cells_centroid_gix ON grid_cells USING GIST (centroid);
CREATE INDEX IF NOT EXISTS grid_cells_aoi_idx      ON grid_cells (aoi_id);

-- IFFI landslide inventory (Inventario dei Fenomeni Franosi in Italia).
CREATE TABLE IF NOT EXISTS iffi_landslides (
    id              text PRIMARY KEY,
    movement_type   text,
    state           text,
    velocity_class  text,
    occurrence_date date,
    geom            geometry(Geometry, 4326) NOT NULL,
    dataset_version_id bigint REFERENCES dataset_versions(id) ON DELETE SET NULL,
    attributes      jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS iffi_geom_gix ON iffi_landslides USING GIST (geom);

-- PAI (Piano di Assetto Idrogeologico) hazard polygons.
CREATE TABLE IF NOT EXISTS pai_hazard (
    id              text PRIMARY KEY,
    hazard_class    text        NOT NULL,
    authority       text,
    geom            geometry(MultiPolygon, 4326) NOT NULL,
    dataset_version_id bigint REFERENCES dataset_versions(id) ON DELETE SET NULL,
    attributes      jsonb       NOT NULL DEFAULT '{}'::jsonb,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS pai_hazard_geom_gix ON pai_hazard USING GIST (geom);

-- Pre-computed susceptibility per cell (continuous 0..1 + class).
CREATE TABLE IF NOT EXISTS susceptibility (
    cell_id         text PRIMARY KEY REFERENCES grid_cells(id) ON DELETE CASCADE,
    score           double precision NOT NULL CHECK (score >= 0 AND score <= 1),
    class           text             NOT NULL,
    model_version   text             NOT NULL,
    computed_at     timestamptz      NOT NULL DEFAULT now(),
    inputs          jsonb            NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS susceptibility_class_idx ON susceptibility (class);

-- Static per-cell factors (slope, aspect, lithology, soil moisture climatology…).
CREATE TABLE IF NOT EXISTS cell_static_factors (
    cell_id         text PRIMARY KEY REFERENCES grid_cells(id) ON DELETE CASCADE,
    slope_deg       double precision,
    aspect_deg      double precision,
    elevation_m     double precision,
    twi             double precision,
    lithology       text,
    land_cover      text,
    distance_to_iffi_m double precision,
    extras          jsonb       NOT NULL DEFAULT '{}'::jsonb,
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- Risk assessments: the output of the scoring engine + MAF agents.
CREATE TABLE IF NOT EXISTS risk_assessments (
    id              bigserial PRIMARY KEY,
    cell_id         text        NOT NULL REFERENCES grid_cells(id) ON DELETE CASCADE,
    computed_at     timestamptz NOT NULL DEFAULT now(),
    horizon         text        NOT NULL,
    score           double precision NOT NULL CHECK (score >= 0 AND score <= 1),
    class           text        NOT NULL,
    factors         jsonb       NOT NULL DEFAULT '{}'::jsonb,
    explanation     jsonb       NOT NULL DEFAULT '{}'::jsonb,
    pipeline_version text       NOT NULL,
    dataset_versions bigint[]   NOT NULL DEFAULT ARRAY[]::bigint[]
);
CREATE INDEX IF NOT EXISTS risk_assessments_cell_idx
    ON risk_assessments (cell_id, computed_at DESC);
CREATE INDEX IF NOT EXISTS risk_assessments_horizon_idx
    ON risk_assessments (horizon, computed_at DESC);
