-- 010_ml_tables.sql
--
-- V2 — ML engine + feature store + InSAR EGMS.
--
-- Tables:
--   training_samples       — point-in-time-correct (cell_id, valuation_time)
--                            feature vectors + binary label + split_block
--                            for spatial-block CV.
--   cell_insar_features    — Copernicus EGMS aggregated to per-cell
--                            velocity + acceleration; low-cadence (yearly).
--   model_runs             — per-cell challenger predictions captured in
--                            shadow mode; used for live evaluation +
--                            drift monitoring. Mirrors risk_assessments
--                            but tagged with model_uri so we can compare
--                            multiple candidates.

-- ---------------------------------------------------------------------------
-- training_samples — feature store (offline)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS training_samples (
    id                  bigserial PRIMARY KEY,
    cell_id             text NOT NULL REFERENCES grid_cells(id) ON DELETE CASCADE,
    valuation_time      timestamptz NOT NULL,
    label               smallint NOT NULL,                -- 0 = background, 1 = positive
    label_source        text NOT NULL,                    -- italica | iffi | background
    -- The features blob mirrors CellFeatureBundle's structure. Stored as
    -- JSONB so V2 schema evolution doesn't break the table; the loader
    -- coerces it back into a typed feature row.
    features            jsonb NOT NULL DEFAULT '{}'::jsonb,
    -- Spatial-block ID for CV — populated by ml.feature_store at
    -- extraction time. Coarse grid in EPSG:4326 (LIMEN_TRAINING__SPATIAL_BLOCK_DEG).
    split_block         text NOT NULL,
    dataset_version_id  bigint REFERENCES dataset_versions(id) ON DELETE SET NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    -- One sample per (cell_id, valuation_time, label_source); rebuilding
    -- the dataset is idempotent.
    UNIQUE (cell_id, valuation_time, label_source)
);
CREATE INDEX IF NOT EXISTS training_samples_label_idx        ON training_samples (label);
CREATE INDEX IF NOT EXISTS training_samples_block_idx        ON training_samples (split_block);
CREATE INDEX IF NOT EXISTS training_samples_valuation_idx
    ON training_samples (valuation_time DESC);

-- ---------------------------------------------------------------------------
-- cell_insar_features — EGMS-derived InSAR features (V2.1)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cell_insar_features (
    cell_id             text PRIMARY KEY REFERENCES grid_cells(id) ON DELETE CASCADE,
    insar_velocity_mmy  double precision,                 -- mm / year
    insar_accel_mmy2    double precision,                 -- mm / year^2
    scatterer_count     integer NOT NULL DEFAULT 0,
    period_start        date,
    period_end          date,
    dataset_version_id  bigint REFERENCES dataset_versions(id) ON DELETE SET NULL,
    updated_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS cell_insar_features_velocity_idx
    ON cell_insar_features (insar_velocity_mmy);

-- ---------------------------------------------------------------------------
-- model_runs — challenger predictions captured in shadow mode
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS model_runs (
    id                  bigserial PRIMARY KEY,
    cell_id             text NOT NULL REFERENCES grid_cells(id) ON DELETE CASCADE,
    computed_at         timestamptz NOT NULL DEFAULT now(),
    model_uri           text NOT NULL,                    -- mlflow:/models/limen-landslide-ml/Production
    model_version       text NOT NULL,
    role                text NOT NULL,                    -- champion | challenger
    probability         double precision NOT NULL CHECK (probability BETWEEN 0.0 AND 1.0),
    risk_class          text NOT NULL,                    -- None / Low / Moderate / High / VeryHigh
    breakdown           jsonb NOT NULL DEFAULT '{}'::jsonb,
    valuation_time      timestamptz NOT NULL,
    aoi_id              text REFERENCES aoi(id) ON DELETE SET NULL,
    UNIQUE (cell_id, computed_at, role, model_uri)
);
CREATE INDEX IF NOT EXISTS model_runs_role_time_idx
    ON model_runs (role, computed_at DESC);
CREATE INDEX IF NOT EXISTS model_runs_cell_time_idx
    ON model_runs (cell_id, computed_at DESC);
CREATE INDEX IF NOT EXISTS model_runs_aoi_time_idx
    ON model_runs (aoi_id, computed_at DESC);
