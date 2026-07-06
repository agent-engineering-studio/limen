-- Predictive-alert dedup ledger, separate from alert_dispatches on
-- purpose: forecast alerts must NEVER mask (or be masked by) the
-- operational per-cell dedup. One row per dispatched forecast alert,
-- keyed at AOI + horizon granularity.

CREATE TABLE IF NOT EXISTS forecast_dispatches (
    id              bigserial PRIMARY KEY,
    aoi_id          text NOT NULL REFERENCES aoi(id) ON DELETE CASCADE,
    horizon_h       integer NOT NULL,
    max_level       text NOT NULL,
    max_score       double precision NOT NULL,
    cells_alerted   integer NOT NULL,
    channels        jsonb NOT NULL DEFAULT '{}'::jsonb,
    summary         text,
    dispatched_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS forecast_dispatches_aoi_time_idx
    ON forecast_dispatches (aoi_id, horizon_h, dispatched_at DESC);
