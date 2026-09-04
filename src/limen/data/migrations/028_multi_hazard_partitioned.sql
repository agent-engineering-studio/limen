-- Hazard as a first-class dimension + daily partitioning of the hot tables.
-- Issue #82 (Fase 1a di #57); absorbs #79.
--
-- Two changes that must land together because both rebuild
-- `risk_assessments`/`model_runs` and every object that reads them. Doing
-- them in two passes would mean copying the data twice and recreating the
-- same seven dependent objects twice.
--
-- 1. `hazard_type` on every table that records or dedups a risk statement,
--    backfilled to 'landslide'. `hazards` is the lookup that mv_latest_risk
--    cross-joins, so enabling a hazard is a row update, not a DDL change.
-- 2. Daily RANGE partitioning on `computed_at`. Retention becomes
--    DROP PARTITION instead of DELETE batches over a table that grows
--    ~15 GB/day (risk_assessments) and ~1 GB/day (model_runs).
--
-- Data handling: rows are copied in-transaction. Measured on the dedicated
-- server at 3.4M rows / 2.7 GB (~2 days of sweeps, retention is 14) the copy
-- is seconds. The hot tables never hold more than the retention window
-- because the cleanup job runs every few minutes, so the copy is bounded by
-- design; there is no historical archive here to move.
--
-- Granularity change (BREAKING for direct SQL consumers): mv_latest_risk now
-- has one row per (cell_id, hazard_type). Every object that reads it and
-- counts cells filters on the default hazard so today's numbers are
-- unchanged; adding a hazard in Fase 2 means revisiting each of them.

-- ---------------------------------------------------------------------------
-- 1. Hazard type + lookup
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'hazard_type') THEN
        CREATE TYPE hazard_type AS ENUM ('landslide', 'flood', 'wildfire');
    END IF;
END $$;

-- `enabled` drives the CROSS JOIN in mv_latest_risk: the view cannot read
-- application settings, so the database needs its own copy of the truth.
-- HAZARDS__ENABLED stays the gate for the Python side; the API logs a
-- warning when the two drift apart.
CREATE TABLE IF NOT EXISTS hazards (
    hazard   hazard_type PRIMARY KEY,
    label_it text NOT NULL,
    enabled  boolean NOT NULL DEFAULT false
);
INSERT INTO hazards (hazard, label_it, enabled) VALUES
    ('landslide', 'Frana',     true),
    ('flood',     'Alluvione', false),
    ('wildfire',  'Incendio',  false)
ON CONFLICT (hazard) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 2. Partition helpers
-- ---------------------------------------------------------------------------
-- One partition per UTC day, named <table>_YYYYMMDD. The retention job
-- derives the partition name from the date, so the naming is load-bearing.
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
            EXECUTE format(
                'CREATE TABLE public.%I PARTITION OF public.%I '
                'FOR VALUES FROM (%L) TO (%L)',
                part, p_table, d::text, (d + 1)::text
            );
            created := created + 1;
        END IF;
        d := d + 1;
    END LOOP;
    RETURN created;
END $$;

COMMENT ON FUNCTION ensure_partitions(text, date, date) IS
'Crea le partizioni giornaliere mancanti di p_table nell''intervallo [p_from, p_to]. Idempotente.';

CREATE OR REPLACE FUNCTION ensure_partitions(p_table text, p_days_ahead integer DEFAULT 7)
RETURNS integer
LANGUAGE sql
AS $$
    SELECT ensure_partitions(p_table, current_date, (current_date + p_days_ahead)::date);
$$;

COMMENT ON FUNCTION ensure_partitions(text, integer) IS
'Crea le partizioni giornaliere da oggi a oggi+p_days_ahead. Chiamata all''avvio e dal job di manutenzione.';

-- Retention: dropping a whole partition replaces the DELETE ... LIMIT batches
-- the cleanup job used to run over a table that grows ~15 GB/day. The DDL
-- lives here rather than being assembled as a string in Python.
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
          -- Only the dated partitions ensure_partitions() creates; never the
          -- DEFAULT one, whose contents signal a missing partition instead.
          AND c.relname ~ ('^' || p_table || '_[0-9]{8}$')
          AND to_date(right(c.relname, 8), 'YYYYMMDD')
              < (current_date - p_retention_days)
    LOOP
        EXECUTE format('DROP TABLE public.%I', part.relname);
        dropped := dropped + 1;
    END LOOP;
    RETURN dropped;
END $$;

COMMENT ON FUNCTION drop_expired_partitions(text, integer) IS
'Elimina le partizioni giornaliere di p_table più vecchie di p_retention_days. 0 = conserva tutto.';

-- ---------------------------------------------------------------------------
-- 3. Drop the objects that read the hot tables (recreated in §7)
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS v_shadow_divergence_tiles;
DROP VIEW IF EXISTS v_shadow_comparison;
DROP VIEW IF EXISTS v_risk_tiles;
DROP VIEW IF EXISTS v_region_tiles;
DROP MATERIALIZED VIEW IF EXISTS mv_comune_risk;
DROP MATERIALIZED VIEW IF EXISTS mv_latest_risk;
-- The 4-argument signature must go explicitly: adding a defaulted 5th
-- parameter creates a *second* function, and an exact 4-arg call would keep
-- resolving to the old body.
DROP FUNCTION IF EXISTS public.risk_at(integer, integer, integer, integer);

-- ---------------------------------------------------------------------------
-- 4. risk_assessments → partitioned + hazard_type
-- ---------------------------------------------------------------------------
-- The legacy table is renamed (not copied out of the way) so the new table
-- can take the canonical name immediately: ensure_partitions() derives
-- partition names from the parent, and renaming a parent afterwards would
-- leave partitions called risk_assessments_new_YYYYMMDD.
ALTER TABLE risk_assessments RENAME TO risk_assessments_legacy;
ALTER TABLE risk_assessments_legacy
    RENAME CONSTRAINT risk_assessments_pkey TO risk_assessments_legacy_pkey;
ALTER INDEX risk_assessments_cell_idx    RENAME TO risk_assessments_legacy_cell_idx;
ALTER INDEX risk_assessments_horizon_idx RENAME TO risk_assessments_legacy_horizon_idx;

CREATE TABLE risk_assessments (
    id               bigint GENERATED BY DEFAULT AS IDENTITY,
    cell_id          text        NOT NULL REFERENCES grid_cells(id) ON DELETE CASCADE,
    computed_at      timestamptz NOT NULL DEFAULT now(),
    hazard_type      hazard_type NOT NULL DEFAULT 'landslide',
    horizon          text        NOT NULL,
    score            double precision NOT NULL CHECK (score >= 0 AND score <= 1),
    class            text        NOT NULL,
    factors          jsonb       NOT NULL DEFAULT '{}'::jsonb,
    explanation      jsonb       NOT NULL DEFAULT '{}'::jsonb,
    pipeline_version text        NOT NULL,
    dataset_versions bigint[]    NOT NULL DEFAULT ARRAY[]::bigint[],
    -- A partitioned table's primary key must contain the partition key.
    PRIMARY KEY (id, computed_at)
) PARTITION BY RANGE (computed_at);

CREATE INDEX risk_assessments_cell_hazard_idx
    ON risk_assessments (cell_id, hazard_type, computed_at DESC);
CREATE INDEX risk_assessments_hazard_horizon_idx
    ON risk_assessments (hazard_type, horizon, computed_at DESC);

-- Safety net for a row that arrives before ensure_partitions() has run.
-- Rows landing here are a bug, not a normal state: the startup check logs
-- `partitions.default_not_empty` when it is non-empty.
CREATE TABLE risk_assessments_default PARTITION OF risk_assessments DEFAULT;

-- Partitions for the rows about to be copied, plus a week ahead.
DO $$
DECLARE lo date; hi date;
BEGIN
    SELECT min(computed_at)::date, max(computed_at)::date
      INTO lo, hi FROM risk_assessments_legacy;
    IF lo IS NOT NULL THEN
        PERFORM ensure_partitions('risk_assessments', lo, hi);
    END IF;
END $$;
SELECT ensure_partitions('risk_assessments', 7);

INSERT INTO risk_assessments (
    id, cell_id, computed_at, hazard_type, horizon, score, class,
    factors, explanation, pipeline_version, dataset_versions
)
SELECT id, cell_id, computed_at, 'landslide', horizon, score, class,
       factors, explanation, pipeline_version, dataset_versions
FROM risk_assessments_legacy;

-- Explicit ids were inserted, so the identity sequence must catch up.
SELECT setval(
    pg_get_serial_sequence('risk_assessments', 'id'),
    GREATEST(COALESCE((SELECT max(id) FROM risk_assessments), 0), 1)
);

DROP TABLE risk_assessments_legacy;

-- New writes must name the hazard explicitly; the default existed only to
-- backfill the copied rows.
ALTER TABLE risk_assessments ALTER COLUMN hazard_type DROP DEFAULT;

-- ---------------------------------------------------------------------------
-- 5. model_runs → partitioned + hazard_type
-- ---------------------------------------------------------------------------
ALTER TABLE model_runs RENAME TO model_runs_legacy;
ALTER TABLE model_runs_legacy RENAME CONSTRAINT model_runs_pkey TO model_runs_legacy_pkey;
ALTER TABLE model_runs_legacy
    RENAME CONSTRAINT model_runs_cell_id_computed_at_role_model_uri_key
    TO model_runs_legacy_dedup_key;
ALTER INDEX model_runs_role_time_idx RENAME TO model_runs_legacy_role_time_idx;
ALTER INDEX model_runs_cell_time_idx RENAME TO model_runs_legacy_cell_time_idx;
ALTER INDEX model_runs_aoi_time_idx  RENAME TO model_runs_legacy_aoi_time_idx;

CREATE TABLE model_runs (
    id             bigint GENERATED BY DEFAULT AS IDENTITY,
    cell_id        text NOT NULL REFERENCES grid_cells(id) ON DELETE CASCADE,
    computed_at    timestamptz NOT NULL DEFAULT now(),
    hazard_type    hazard_type NOT NULL DEFAULT 'landslide',
    model_uri      text NOT NULL,
    model_version  text NOT NULL,
    role           text NOT NULL,
    probability    double precision NOT NULL CHECK (probability BETWEEN 0.0 AND 1.0),
    risk_class     text NOT NULL,
    breakdown      jsonb NOT NULL DEFAULT '{}'::jsonb,
    valuation_time timestamptz NOT NULL,
    aoi_id         text REFERENCES aoi(id) ON DELETE SET NULL,
    PRIMARY KEY (id, computed_at),
    UNIQUE (cell_id, hazard_type, computed_at, role, model_uri)
) PARTITION BY RANGE (computed_at);

CREATE INDEX model_runs_role_time_idx   ON model_runs (role, computed_at DESC);
CREATE INDEX model_runs_cell_time_idx   ON model_runs (cell_id, hazard_type, computed_at DESC);
CREATE INDEX model_runs_aoi_time_idx    ON model_runs (aoi_id, computed_at DESC);
CREATE INDEX model_runs_hazard_time_idx ON model_runs (hazard_type, computed_at DESC);

CREATE TABLE model_runs_default PARTITION OF model_runs DEFAULT;

DO $$
DECLARE lo date; hi date;
BEGIN
    SELECT min(computed_at)::date, max(computed_at)::date
      INTO lo, hi FROM model_runs_legacy;
    IF lo IS NOT NULL THEN
        PERFORM ensure_partitions('model_runs', lo, hi);
    END IF;
END $$;
SELECT ensure_partitions('model_runs', 7);

INSERT INTO model_runs (
    id, cell_id, computed_at, hazard_type, model_uri, model_version, role,
    probability, risk_class, breakdown, valuation_time, aoi_id
)
SELECT id, cell_id, computed_at, 'landslide', model_uri, model_version, role,
       probability, risk_class, breakdown, valuation_time, aoi_id
FROM model_runs_legacy;

SELECT setval(
    pg_get_serial_sequence('model_runs', 'id'),
    GREATEST(COALESCE((SELECT max(id) FROM model_runs), 0), 1)
);

DROP TABLE model_runs_legacy;
ALTER TABLE model_runs ALTER COLUMN hazard_type DROP DEFAULT;

-- ---------------------------------------------------------------------------
-- 6. Small tables: column + key
-- ---------------------------------------------------------------------------
-- norm_stats: the calibration stats are per hazard, so the hazard belongs in
-- the primary key next to the factor name.
ALTER TABLE norm_stats ADD COLUMN IF NOT EXISTS hazard_type hazard_type NOT NULL DEFAULT 'landslide';
ALTER TABLE norm_stats DROP CONSTRAINT IF EXISTS norm_stats_pkey;
ALTER TABLE norm_stats ADD PRIMARY KEY (aoi_id, hazard_type, factor, model_version);
ALTER TABLE norm_stats ALTER COLUMN hazard_type DROP DEFAULT;

-- training_samples: one sample per (cell, hazard, time, source). A flood
-- truth set and a landslide truth set can name the same cell and hour.
ALTER TABLE training_samples ADD COLUMN IF NOT EXISTS hazard_type hazard_type NOT NULL DEFAULT 'landslide';
ALTER TABLE training_samples
    DROP CONSTRAINT IF EXISTS training_samples_cell_id_valuation_time_label_source_key;
ALTER TABLE training_samples
    ADD CONSTRAINT training_samples_cell_hazard_time_source_key
    UNIQUE (cell_id, hazard_type, valuation_time, label_source);
CREATE INDEX IF NOT EXISTS training_samples_hazard_idx ON training_samples (hazard_type);
ALTER TABLE training_samples ALTER COLUMN hazard_type DROP DEFAULT;

-- Dedup ledgers: the hazard enters the key, otherwise a landslide alert
-- would suppress a flood alert on the same cell inside the window.
ALTER TABLE alert_dispatches ADD COLUMN IF NOT EXISTS hazard_type hazard_type NOT NULL DEFAULT 'landslide';
DROP INDEX IF EXISTS alert_dispatches_cell_time_idx;
CREATE INDEX alert_dispatches_cell_hazard_time_idx
    ON alert_dispatches (cell_id, hazard_type, dispatched_at DESC);
CREATE INDEX IF NOT EXISTS alert_dispatches_hazard_time_idx
    ON alert_dispatches (hazard_type, dispatched_at DESC);
ALTER TABLE alert_dispatches ALTER COLUMN hazard_type DROP DEFAULT;

ALTER TABLE forecast_dispatches ADD COLUMN IF NOT EXISTS hazard_type hazard_type NOT NULL DEFAULT 'landslide';
DROP INDEX IF EXISTS forecast_dispatches_aoi_time_idx;
CREATE INDEX forecast_dispatches_aoi_hazard_time_idx
    ON forecast_dispatches (aoi_id, hazard_type, horizon_h, dispatched_at DESC);
ALTER TABLE forecast_dispatches ALTER COLUMN hazard_type DROP DEFAULT;

-- ---------------------------------------------------------------------------
-- 7. Rebuild the dependent objects
-- ---------------------------------------------------------------------------
-- One row per (cell, enabled hazard). The CROSS JOIN is what makes the
-- unique index valid: a LEFT JOIN alone would leave hazard_type NULL on
-- unassessed cells, and NULLs are distinct in a unique index, so the same
-- cell could appear twice and every tile would draw it twice.
CREATE MATERIALIZED VIEW mv_latest_risk AS
WITH ranked AS (
    SELECT ra.*,
           ROW_NUMBER() OVER (
               PARTITION BY ra.cell_id, ra.hazard_type
               ORDER BY ra.computed_at DESC
           ) AS rn
    FROM risk_assessments ra
)
SELECT g.id               AS cell_id,
       h.hazard           AS hazard_type,
       g.aoi_id           AS aoi_id,
       g.geom             AS geom,
       g.centroid         AS centroid,
       g.area_km2         AS area_km2,
       r.score            AS risk_score,
       r.class            AS risk_level,
       r.horizon          AS horizon,
       r.pipeline_version AS pipeline_version,
       r.computed_at      AS computed_at,
       r.factors          AS factors,
       r.explanation      AS explanation
FROM grid_cells g
CROSS JOIN hazards h
LEFT JOIN ranked r
       ON r.cell_id = g.id AND r.hazard_type = h.hazard AND r.rn = 1
WHERE h.enabled
WITH NO DATA;

CREATE UNIQUE INDEX mv_latest_risk_cell_hazard_idx
    ON mv_latest_risk (cell_id, hazard_type);
CREATE INDEX mv_latest_risk_aoi_idx      ON mv_latest_risk (aoi_id);
CREATE INDEX mv_latest_risk_geom_gix     ON mv_latest_risk USING GIST (geom);
CREATE INDEX mv_latest_risk_level_idx    ON mv_latest_risk (risk_level);
CREATE INDEX mv_latest_risk_hazard_level_idx
    ON mv_latest_risk (hazard_type, risk_level);

REFRESH MATERIALIZED VIEW mv_latest_risk;

-- Comune rollup. `exposure_rank` reads factors->>'e', a key that only the
-- landslide breakdown has: another reason the join is pinned to the default
-- hazard until Fase 2 gives each hazard its own exposure term.
CREATE MATERIALIZED VIEW mv_comune_risk AS
SELECT
    c.istat_code,
    c.name,
    c.aoi_id,
    COUNT(m.cell_id)                                            AS n_cells,
    COUNT(*) FILTER (WHERE m.risk_level = 'None')               AS n_none,
    COUNT(*) FILTER (WHERE m.risk_level = 'Low')                AS n_low,
    COUNT(*) FILTER (WHERE m.risk_level = 'Moderate')           AS n_moderate,
    COUNT(*) FILTER (WHERE m.risk_level = 'High')               AS n_high,
    COUNT(*) FILTER (WHERE m.risk_level = 'VeryHigh')           AS n_veryhigh,
    COUNT(*) FILTER (WHERE m.risk_level IN ('High','VeryHigh')) AS n_alert,
    MAX(m.risk_score)                                           AS max_score,
    COALESCE(
        (array_agg(m.risk_level ORDER BY m.risk_score DESC NULLS LAST))[1],
        'None'
    )                                                           AS worst_class,
    COALESCE(SUM((m.factors->>'e')::double precision)
             FILTER (WHERE m.risk_level IN ('High','VeryHigh')), 0) AS exposure_rank,
    c.geom,
    c.centroid
FROM comuni c
LEFT JOIN cell_comune cc ON cc.istat_code = c.istat_code
LEFT JOIN mv_latest_risk m
       ON m.cell_id = cc.cell_id
      AND m.hazard_type = 'landslide'
      AND m.risk_score IS NOT NULL
GROUP BY c.istat_code, c.name, c.aoi_id, c.geom, c.centroid
WITH NO DATA;

CREATE UNIQUE INDEX mv_comune_risk_pk    ON mv_comune_risk (istat_code);
CREATE INDEX mv_comune_risk_geom_gix     ON mv_comune_risk USING GIST (geom);
CREATE INDEX mv_comune_risk_aoi_idx      ON mv_comune_risk (aoi_id);

REFRESH MATERIALIZED VIEW mv_comune_risk;

-- Backwards-compatible tile source for pg_tileserv: the frontend loads
-- `public.v_risk_tiles` by name. It stays pinned to the default hazard;
-- the multi-hazard tile surface is risk_at(), which takes a parameter.
CREATE OR REPLACE VIEW v_risk_tiles AS
SELECT cell_id, aoi_id, hazard_type, risk_score, risk_level, computed_at, geom
FROM mv_latest_risk
WHERE hazard_type = 'landslide';

CREATE OR REPLACE VIEW v_region_tiles AS
SELECT
    a.id                                            AS aoi_id,
    a.name,
    COUNT(m.cell_id)                                AS cells,
    COUNT(*) FILTER (WHERE m.risk_level = 'Moderate')            AS moderate,
    COUNT(*) FILTER (WHERE m.risk_level IN ('High', 'VeryHigh')) AS high_or_above,
    MAX(m.risk_score)                               AS max_score,
    COALESCE(
        (array_agg(m.risk_level ORDER BY m.risk_score DESC NULLS LAST))[1],
        'None'
    )                                               AS risk_level,
    a.geom
FROM aoi a
LEFT JOIN mv_latest_risk m
       ON m.aoi_id = a.id
      AND m.hazard_type = 'landslide'
      AND m.risk_score IS NOT NULL
GROUP BY a.id, a.name, a.geom;

CREATE OR REPLACE VIEW v_shadow_comparison AS
WITH champion AS (
    SELECT DISTINCT ON (cell_id, hazard_type)
           cell_id, hazard_type, score, class, computed_at
    FROM risk_assessments
    ORDER BY cell_id, hazard_type, computed_at DESC
),
challenger AS (
    SELECT DISTINCT ON (cell_id, hazard_type)
           cell_id, hazard_type, probability, risk_class, model_version, computed_at
    FROM model_runs
    WHERE role = 'challenger'
    ORDER BY cell_id, hazard_type, computed_at DESC
)
SELECT
    ch.cell_id,
    ch.hazard_type,
    g.aoi_id,
    ch.score                    AS champion_score,
    ch.class                    AS champion_class,
    ml.probability              AS ml_probability,
    ml.risk_class               AS ml_class,
    ml.probability - ch.score   AS divergence,
    ml.model_version,
    ch.computed_at              AS champion_at,
    ml.computed_at              AS challenger_at
FROM champion ch
JOIN challenger ml USING (cell_id, hazard_type)
JOIN grid_cells g ON g.id = ch.cell_id;

CREATE OR REPLACE VIEW v_shadow_divergence_tiles AS
SELECT s.cell_id, s.hazard_type, s.aoi_id, s.divergence, g.geom
FROM v_shadow_comparison s
JOIN grid_cells g ON g.id = s.cell_id;

-- `p_hazard` is appended last and defaulted so pg_tileserv URLs that pass
-- only z/x/y/hours_ago keep working.
CREATE OR REPLACE FUNCTION public.risk_at(
    z integer, x integer, y integer,
    hours_ago integer DEFAULT 0,
    p_hazard hazard_type DEFAULT 'landslide'
) RETURNS bytea AS $$
WITH bounds AS (
    SELECT ST_TileEnvelope(z, x, y) AS b
),
cells AS (
    SELECT g.id, g.geom
    FROM grid_cells g, bounds
    WHERE ST_Transform(g.geom, 3857) && bounds.b
),
latest AS (
    SELECT DISTINCT ON (ra.cell_id) ra.cell_id, ra.score, ra.class
    FROM risk_assessments ra
    JOIN cells c ON c.id = ra.cell_id
    WHERE ra.hazard_type = p_hazard
      AND ra.computed_at <= now() - make_interval(hours => GREATEST(hours_ago, 0))
    ORDER BY ra.cell_id, ra.computed_at DESC
),
mvt AS (
    SELECT ST_AsMVTGeom(ST_Transform(c.geom, 3857), bounds.b) AS geom,
           c.id      AS cell_id,
           l.score   AS risk_score,
           l.class   AS risk_level
    FROM cells c
    JOIN latest l ON l.cell_id = c.id, bounds
)
SELECT ST_AsMVT(mvt.*, 'public.v_risk_tiles', 4096, 'geom') FROM mvt;
$$ LANGUAGE sql STABLE PARALLEL SAFE;

COMMENT ON FUNCTION public.risk_at IS
'Vector tiles dello stato di rischio per cella a N ore fa (timeline), per hazard.';

-- ---------------------------------------------------------------------------
-- 8. Refresh helper
-- ---------------------------------------------------------------------------
-- Recreated because both materialized views were dropped above. This body
-- restores the debounce that migration 017 introduced and migration 026
-- dropped when it redefined the function to chain the comune refresh: the
-- 5-minute guard has been inert since 026, so every PersistResult call has
-- been doing a full CONCURRENTLY refresh of 312k rows plus the comune
-- rollup. Return codes keep the semantics callers rely on
-- (1 concurrent, 0 debounced or blocking, -1 failed).
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
            RAISE NOTICE 'refresh_mv_latest_risk failed: %', SQLERRM;
            RETURN -1;
    END;

    -- Comune depends on the freshly refreshed latest view. Best-effort:
    -- a comune-refresh failure must not mask a successful latest refresh.
    PERFORM refresh_mv_comune_risk();
    RETURN latest_rc;
END $$;
