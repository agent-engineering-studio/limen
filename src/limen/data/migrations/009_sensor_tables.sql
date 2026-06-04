-- 009_sensor_tables.sql
--
-- V1.5 — IoT in-situ. Storage for SensorThings-aligned observations
-- and the per-cell hourly rollup the scoring engine reads.
--
-- Tables (per project doc §3.3.8):
--   sensor_devices         — Thing registry (device + cell binding +
--                            calibration metadata + lifecycle status)
--   sensor_observations    — raw observation stream, range-partitioned
--                            by phenomenon_time so each month is a
--                            cheap drop-target
--   sensor_features_hourly — pre-aggregated per-cell hourly features
--                            that the workflow's SensorFetchExecutor
--                            consumes (velocity, acceleration,
--                            inverse-velocity, etc.)
--
-- Helper: ensure_sensor_partition_for_month(date) creates the month
-- partition idempotently. Used by the migration (seed window) and by
-- the V1.5 APScheduler "partition rollover" job each month.

-- ---------------------------------------------------------------------------
-- sensor_devices — the SensorThings "Thing"
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sensor_devices (
    id              text PRIMARY KEY,
    device_type     text NOT NULL,
    cell_id         text REFERENCES grid_cells(id) ON DELETE SET NULL,
    location        geometry(Point, 4326) NOT NULL,
    calibration     jsonb NOT NULL DEFAULT '{}'::jsonb,
    status          text NOT NULL DEFAULT 'online',
    last_seen_at    timestamptz,
    metadata        jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT sensor_devices_status_chk
        CHECK (status IN ('online', 'offline', 'quarantined'))
);
CREATE INDEX IF NOT EXISTS sensor_devices_cell_idx   ON sensor_devices (cell_id);
CREATE INDEX IF NOT EXISTS sensor_devices_status_idx ON sensor_devices (status);
CREATE INDEX IF NOT EXISTS sensor_devices_geom_gix   ON sensor_devices USING GIST (location);

-- ---------------------------------------------------------------------------
-- sensor_observations — partitioned raw stream
-- ---------------------------------------------------------------------------
-- Each monthly partition is `sensor_observations_yYYYY_mMM`. The
-- composite primary key includes phenomenon_time because the partition
-- key MUST be part of the PK.
CREATE TABLE IF NOT EXISTS sensor_observations (
    id                  bigserial,
    device_id           text NOT NULL REFERENCES sensor_devices(id) ON DELETE CASCADE,
    observed_property   text NOT NULL,
    phenomenon_time     timestamptz NOT NULL,
    result_value        double precision NOT NULL,
    result_unit         text NOT NULL,
    raw_value           double precision,
    quality             text NOT NULL DEFAULT 'ok',
    metadata            jsonb NOT NULL DEFAULT '{}'::jsonb,
    received_at         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id, phenomenon_time),
    CONSTRAINT sensor_observations_quality_chk
        CHECK (quality IN ('ok', 'spike', 'flatline', 'gap', 'range', 'unit'))
) PARTITION BY RANGE (phenomenon_time);
CREATE INDEX IF NOT EXISTS sensor_observations_device_time_idx
    ON sensor_observations (device_id, phenomenon_time DESC);
CREATE INDEX IF NOT EXISTS sensor_observations_property_time_idx
    ON sensor_observations (observed_property, phenomenon_time DESC);
CREATE INDEX IF NOT EXISTS sensor_observations_quality_idx
    ON sensor_observations (quality);


-- ---------------------------------------------------------------------------
-- Partition helper — creates one month partition idempotently.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION ensure_sensor_partition_for_month(p_month date)
    RETURNS text
    LANGUAGE plpgsql
AS $$
DECLARE
    start_ts  timestamptz := date_trunc('month', p_month);
    end_ts    timestamptz := date_trunc('month', p_month) + interval '1 month';
    part_name text := format(
        'sensor_observations_y%s_m%s',
        to_char(start_ts, 'YYYY'),
        to_char(start_ts, 'MM')
    );
BEGIN
    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF sensor_observations '
        'FOR VALUES FROM (%L) TO (%L)',
        part_name, start_ts, end_ts
    );
    RETURN part_name;
END
$$;


-- ---------------------------------------------------------------------------
-- Seed window: current month + ±6 months. Idempotent: the helper uses
-- CREATE TABLE IF NOT EXISTS, so re-running the migration is a no-op.
-- An APScheduler "partition rollover" job extends the window monthly.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    offset_m integer;
BEGIN
    FOR offset_m IN -6 .. 6 LOOP
        PERFORM ensure_sensor_partition_for_month(
            (date_trunc('month', now()) + (offset_m || ' month')::interval)::date
        );
    END LOOP;
END
$$;


-- ---------------------------------------------------------------------------
-- sensor_features_hourly — per-cell aggregate read by the workflow
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sensor_features_hourly (
    cell_id              text NOT NULL REFERENCES grid_cells(id) ON DELETE CASCADE,
    bucket               timestamptz NOT NULL,
    rainfall_mm          double precision,
    pore_pressure_kpa    double precision,
    soil_moisture        double precision,
    displacement_mm      double precision,
    velocity_mmd         double precision,
    acceleration_mmd2    double precision,
    inverse_velocity     double precision,
    sample_count         integer NOT NULL DEFAULT 0,
    last_observation_at  timestamptz,
    updated_at           timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (cell_id, bucket)
);
CREATE INDEX IF NOT EXISTS sensor_features_hourly_bucket_idx
    ON sensor_features_hourly (bucket DESC);
CREATE INDEX IF NOT EXISTS sensor_features_hourly_cell_bucket_idx
    ON sensor_features_hourly (cell_id, bucket DESC);
