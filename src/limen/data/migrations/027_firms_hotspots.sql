-- 027_firms_hotspots.sql
--
-- NASA FIRMS active-fire hotspots (VIIRS 375 m / MODIS 1 km, NRT).
--
-- Complementary to `fire_perimeters` (EFFIS): perimeters are the
-- consolidated areal truth that arrives days after the event, hotspots
-- are point detections with ~3 h latency. Both feed the post-fire F
-- component of the landslide score; the hotspots additionally drive the
-- event-driven monitoring trigger.
--
-- The primary key is FIRMS' natural key. Coordinates come from the CSV
-- as fixed-decimal strings, so re-parsing the same detection yields
-- bit-identical doubles and the upsert stays idempotent.
--
-- `acquired_at` is redundant with (acq_date, acq_time) but computed once
-- at ingest: the trigger window is expressed in hours, and Postgres
-- cannot fold the date+time+zone expression into a generated column
-- (`timezone(text, timestamp)` is STABLE, not IMMUTABLE).

CREATE TABLE IF NOT EXISTS fire_hotspots (
    source              text NOT NULL,                       -- FIRMS SOURCE (VIIRS_SNPP_NRT, ...)
    acq_date            date NOT NULL,
    acq_time            smallint NOT NULL,                    -- HHMM UTC as reported
    latitude            double precision NOT NULL,
    longitude           double precision NOT NULL,
    acquired_at         timestamptz NOT NULL,
    frp_mw              double precision,                     -- Fire Radiative Power
    confidence          text,                                 -- l/n/h (VIIRS) or 0..100 (MODIS)
    brightness_k        double precision,
    daynight            text,
    satellite           text,
    instrument          text,
    geom                geometry(Point, 4326) NOT NULL,
    dataset_version_id  bigint REFERENCES dataset_versions(id) ON DELETE SET NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source, acq_date, acq_time, latitude, longitude)
);

CREATE INDEX IF NOT EXISTS fire_hotspots_geom_gix ON fire_hotspots USING GIST (geom);
CREATE INDEX IF NOT EXISTS fire_hotspots_acquired_idx ON fire_hotspots (acquired_at DESC);
CREATE INDEX IF NOT EXISTS fire_hotspots_date_idx ON fire_hotspots (acq_date DESC);
