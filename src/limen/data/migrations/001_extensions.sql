-- 001_extensions.sql
--
-- Required:    PostGIS (spatial).
-- Recommended: pgvector (used by later phases; harmless to skip if absent).
-- Optional:    pg_cron. Neon does NOT support it; without it the in-process
--              APScheduler runs the periodic jobs (see core/scheduling.py).
--
-- pgvector and pg_cron are both wrapped in DO-blocks that swallow installation
-- errors, so this migration works on the official Docker image, the arm64
-- community image (no pgvector), and Neon (no pg_cron).

CREATE EXTENSION IF NOT EXISTS postgis;

DO $$
BEGIN
    BEGIN
        CREATE EXTENSION IF NOT EXISTS vector;
    EXCEPTION
        WHEN insufficient_privilege THEN
            RAISE NOTICE 'pgvector requires superuser — skipping (later phases will detect absence)';
        WHEN feature_not_supported THEN
            RAISE NOTICE 'pgvector not supported on this server — skipping';
        WHEN undefined_file THEN
            RAISE NOTICE 'pgvector shared library not installed — skipping';
        WHEN OTHERS THEN
            RAISE NOTICE 'pgvector unavailable (%): skipping', SQLERRM;
    END;
END
$$;

DO $$
BEGIN
    BEGIN
        CREATE EXTENSION IF NOT EXISTS pg_cron;
    EXCEPTION
        WHEN insufficient_privilege THEN
            RAISE NOTICE 'pg_cron requires superuser — skipping (APScheduler will be used)';
        WHEN feature_not_supported THEN
            RAISE NOTICE 'pg_cron not supported on this server — skipping (APScheduler will be used)';
        WHEN undefined_file THEN
            RAISE NOTICE 'pg_cron shared library not installed — skipping (APScheduler will be used)';
        WHEN OTHERS THEN
            RAISE NOTICE 'pg_cron unavailable (%): skipping (APScheduler will be used)', SQLERRM;
    END;
END
$$;
