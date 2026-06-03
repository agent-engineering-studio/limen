-- 006_scoring_engine.sql
--
-- Phase 3 — deterministic V1 scoring engine.
--
-- Adds:
--   * cell_static_factors.s_static (double precision) — the static component
--     S(c) of the risk score, precomputed by `limen calibrate` and read at
--     score time. Storing it once amortises the per-AOI normalisation across
--     thousands of scoring requests.
--   * norm_stats — per-AOI per-factor min/max statistics persisted so that
--     min–max normalisation at score time is reproducible. The (aoi_id,
--     factor, model_version) key lets us keep historical calibrations
--     around for auditability.

ALTER TABLE cell_static_factors ADD COLUMN IF NOT EXISTS s_static double precision
    CHECK (s_static IS NULL OR (s_static >= 0 AND s_static <= 1));

CREATE TABLE IF NOT EXISTS norm_stats (
    aoi_id         text NOT NULL REFERENCES aoi(id) ON DELETE CASCADE,
    factor         text NOT NULL,
    min_value      double precision NOT NULL,
    max_value      double precision NOT NULL,
    model_version  text NOT NULL,
    computed_at    timestamptz NOT NULL DEFAULT now(),
    sample_size    integer,
    extras         jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (aoi_id, factor, model_version)
);
CREATE INDEX IF NOT EXISTS norm_stats_aoi_idx ON norm_stats (aoi_id);
