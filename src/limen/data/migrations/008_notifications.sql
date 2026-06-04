-- 008_notifications.sql
--
-- Phase 7 — multi-channel notification dispatch.
--
-- Adds:
--   * alert_dispatches  — one row per (cell, dispatched_at). The
--     dedup logic queries this table to suppress repeat alerts for
--     the same cell within a configurable window.
--   * cell_static_factors.population_count / buildings_count /
--     infra_density_norm — exposure variables (§2.3 #23–25) used by
--     the AlertDispatchExecutor to compute priority. NULL by default;
--     the ingest pipeline that populates them lands in a later prompt.
--     Priority falls back to the raw score when exposure is unknown.

CREATE TABLE IF NOT EXISTS alert_dispatches (
    id              bigserial PRIMARY KEY,
    cell_id         text NOT NULL REFERENCES grid_cells(id) ON DELETE CASCADE,
    aoi_id          text NOT NULL REFERENCES aoi(id) ON DELETE CASCADE,
    level           text NOT NULL,
    score           double precision NOT NULL,
    priority        double precision NOT NULL,
    channels        jsonb NOT NULL DEFAULT '{}'::jsonb,
    summary         text,
    dispatched_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS alert_dispatches_cell_time_idx
    ON alert_dispatches (cell_id, dispatched_at DESC);
CREATE INDEX IF NOT EXISTS alert_dispatches_aoi_time_idx
    ON alert_dispatches (aoi_id, dispatched_at DESC);
CREATE INDEX IF NOT EXISTS alert_dispatches_level_idx
    ON alert_dispatches (level);


-- ---------------------------------------------------------------------------
-- Exposure columns on cell_static_factors (NULL = unknown → priority
-- falls back to the raw risk score).
-- ---------------------------------------------------------------------------
ALTER TABLE cell_static_factors
    ADD COLUMN IF NOT EXISTS population_count    integer
    CHECK (population_count IS NULL OR population_count >= 0);
ALTER TABLE cell_static_factors
    ADD COLUMN IF NOT EXISTS buildings_count     integer
    CHECK (buildings_count IS NULL OR buildings_count >= 0);
ALTER TABLE cell_static_factors
    ADD COLUMN IF NOT EXISTS infra_density_norm  double precision
    CHECK (infra_density_norm IS NULL OR (infra_density_norm >= 0 AND infra_density_norm <= 1));
