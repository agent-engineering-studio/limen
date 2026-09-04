-- Corrections to migration 028, found in review of issue #82.
--
-- 1. Partition boundaries and names were derived from `current_date`, i.e. the
--    session TimeZone, while the partition key is `timestamptz`. On a server
--    whose TimeZone is not UTC the day a row belongs to and the day the
--    partition is named after disagree, and changing the TimeZone later can
--    make a new partition overlap an existing one. Everything is pinned to UTC
--    now, matching the "one partition per UTC day" contract.
-- 2. `ensure_partitions` is check-then-create, so two callers racing (API boot
--    plus the cleanup tick, or an operator running `limen partitions`) made one
--    of them fail with duplicate_table. The loop now treats that as "already
--    there", which is what the caller means.
-- 3. `refresh_mv_latest_risk()` stamped `refreshed_at` *before* refreshing and
--    left it stamped when the refresh failed, so a transient failure silenced
--    every retry for five minutes. Migration 026 (no debounce) retried
--    immediately. The stamp is now rolled back on failure.
-- 4. `v_risk_tiles` carried a `hazard_type` column that is constant by
--    construction (the view is pinned to landslide). Migration 018 exists
--    precisely to keep the tile payload minimal, so a constant property per
--    feature is pure waste on every tile request.

CREATE OR REPLACE FUNCTION ensure_partitions(p_table text, p_from date, p_to date)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    d       date := p_from;
    part    text;
    created integer := 0;
BEGIN
    WHILE d <= p_to LOOP
        part := format('%s_%s', p_table, to_char(d, 'YYYYMMDD'));
        IF NOT EXISTS (
            SELECT 1 FROM pg_class
            WHERE relname = part AND relnamespace = 'public'::regnamespace
        ) THEN
            BEGIN
                EXECUTE format(
                    'CREATE TABLE public.%I PARTITION OF public.%I '
                    'FOR VALUES FROM (%L) TO (%L)',
                    part, p_table,
                    (d::timestamp AT TIME ZONE 'UTC')::text,
                    ((d + 1)::timestamp AT TIME ZONE 'UTC')::text
                );
                created := created + 1;
            EXCEPTION
                -- Another caller won the race; the partition exists, which is
                -- all this function promises.
                WHEN duplicate_table THEN NULL;
            END;
        END IF;
        d := d + 1;
    END LOOP;
    RETURN created;
END $$;

CREATE OR REPLACE FUNCTION ensure_partitions(p_table text, p_days_ahead integer DEFAULT 7)
RETURNS integer
LANGUAGE sql
AS $$
    SELECT ensure_partitions(
        p_table,
        (now() AT TIME ZONE 'UTC')::date,
        ((now() AT TIME ZONE 'UTC')::date + p_days_ahead)::date
    );
$$;

CREATE OR REPLACE FUNCTION drop_expired_partitions(p_table text, p_retention_days integer)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    part    record;
    dropped integer := 0;
BEGIN
    IF p_retention_days <= 0 THEN
        RETURN 0;
    END IF;
    FOR part IN
        SELECT c.relname
        FROM pg_inherits i
        JOIN pg_class c ON c.oid = i.inhrelid
        WHERE i.inhparent = format('public.%I', p_table)::regclass
          AND c.relname ~ ('^' || p_table || '_[0-9]{8}$')
          AND to_date(right(c.relname, 8), 'YYYYMMDD')
              < ((now() AT TIME ZONE 'UTC')::date - p_retention_days)
    LOOP
        EXECUTE format('DROP TABLE public.%I', part.relname);
        dropped := dropped + 1;
    END LOOP;
    RETURN dropped;
END $$;

CREATE OR REPLACE FUNCTION refresh_mv_latest_risk() RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    last_refresh timestamptz;
    latest_rc    integer;
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
        latest_rc := 1;
    EXCEPTION
        WHEN feature_not_supported THEN
            REFRESH MATERIALIZED VIEW mv_latest_risk;
            latest_rc := 0;
        WHEN OTHERS THEN
            -- Give the stamp back, otherwise one transient failure debounces
            -- every retry for the next five minutes.
            UPDATE mv_refresh_state SET refreshed_at = last_refresh
            WHERE view_name = 'mv_latest_risk';
            RAISE NOTICE 'refresh_mv_latest_risk failed: %', SQLERRM;
            RETURN -1;
    END;

    -- Comune depends on the freshly refreshed latest view. Best-effort:
    -- a comune-refresh failure must not mask a successful latest refresh.
    PERFORM refresh_mv_comune_risk();
    RETURN latest_rc;
END $$;

-- DROP then CREATE: `CREATE OR REPLACE VIEW` can add columns but never remove
-- one. Nothing depends on this view (risk_at() only borrows its name as the
-- MVT layer label), so a plain DROP without CASCADE is the safe form -- it
-- fails loudly if that ever stops being true.
DROP VIEW IF EXISTS v_risk_tiles;
CREATE VIEW v_risk_tiles AS
SELECT cell_id, aoi_id, risk_score, risk_level, computed_at, geom
FROM mv_latest_risk
WHERE hazard_type = 'landslide';
