-- First-boot extension setup. The Limen migration runner is idempotent and
-- will re-run these via `001_extensions.sql`, but providing them here lets
-- newly created clusters be ready before the app connects.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;

-- pg_cron is optional. Attempt to create it but do not fail if unavailable.
DO $$
BEGIN
    BEGIN
        CREATE EXTENSION IF NOT EXISTS pg_cron;
    EXCEPTION
        WHEN OTHERS THEN
            RAISE NOTICE 'pg_cron extension not available — skipping (APScheduler will be used)';
    END;
END
$$;
