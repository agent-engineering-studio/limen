-- 003_cache_table.sql
--
-- Postgres-backed distributed cache used by the application layer.
-- UNLOGGED keeps writes cheap; cache contents are by definition rebuildable.
-- A periodic cleanup deletes expired rows; the cleanup is scheduled by:
--
--   * pg_cron, when available (local Docker), OR
--   * APScheduler in-process, when not (e.g. on Neon).
--
-- We schedule the pg_cron job conditionally via a DO-block so that this
-- migration is safe on Neon, where pg_cron does not exist.

CREATE UNLOGGED TABLE IF NOT EXISTS app_cache (
    key         text        PRIMARY KEY,
    value       jsonb       NOT NULL,
    expires_at  timestamptz NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS app_cache_expires_idx ON app_cache (expires_at);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
        PERFORM cron.schedule(
            'limen_app_cache_cleanup',
            '*/5 * * * *',
            $cleanup$DELETE FROM app_cache WHERE expires_at < now();$cleanup$
        );
        RAISE NOTICE 'pg_cron scheduled: limen_app_cache_cleanup every 5 minutes';
    ELSE
        RAISE NOTICE 'pg_cron not installed — APScheduler will run app_cache cleanup';
    END IF;
END
$$;
