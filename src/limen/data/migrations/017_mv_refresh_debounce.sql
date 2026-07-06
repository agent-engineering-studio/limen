-- Debounce for refresh_mv_latest_risk(): the national hourly sweep calls
-- it after EVERY AOI (20× per sweep), and a concurrent refresh over the
-- 312k-cell view costs minutes on a multi-GB risk_assessments base —
-- the DB ends up refreshing back-to-back and starving every other query.
-- One refresh per window is plenty for the map and the reports.

CREATE TABLE IF NOT EXISTS mv_refresh_state (
    view_name    text PRIMARY KEY,
    refreshed_at timestamptz NOT NULL DEFAULT to_timestamp(0)
);
INSERT INTO mv_refresh_state (view_name) VALUES ('mv_latest_risk')
ON CONFLICT (view_name) DO NOTHING;

CREATE OR REPLACE FUNCTION refresh_mv_latest_risk() RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    last_refresh timestamptz;
BEGIN
    -- FOR UPDATE serialises concurrent callers: the first one refreshes,
    -- the others see the fresh timestamp and return immediately.
    SELECT refreshed_at INTO last_refresh
    FROM mv_refresh_state WHERE view_name = 'mv_latest_risk'
    FOR UPDATE;

    IF last_refresh > now() - interval '5 minutes' THEN
        RETURN 0;
    END IF;

    UPDATE mv_refresh_state SET refreshed_at = now()
    WHERE view_name = 'mv_latest_risk';

    BEGIN
        REFRESH MATERIALIZED VIEW CONCURRENTLY mv_latest_risk;
        RETURN 1;
    EXCEPTION
        WHEN feature_not_supported THEN
            -- First call before any non-concurrent refresh.
            REFRESH MATERIALIZED VIEW mv_latest_risk;
            RETURN 1;
    END;
END $$;
