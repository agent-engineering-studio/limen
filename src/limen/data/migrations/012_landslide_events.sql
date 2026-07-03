-- 012_landslide_events.sql
--
-- Dated landslide-event catalogue, distinct from the IFFI inventory.
--
-- `iffi_landslides` is a static *inventory* (polygons, mostly undated)
-- and feeds the per-cell IFFI density used for the S component. Event
-- catalogues (ITALICA / e-ITALICA — rainfall-induced landslides with a
-- date, time and point location) are a different concept: they are the
-- truth set for the §2.5 backtest. Keeping them here avoids polluting
-- `iffi_density_500` with point events.
--
-- Points are stored in EPSG:4326. `event_time` is UTC (parsed from the
-- catalogue's UTC_date); `temporal_accuracy` records how precise it is
-- (T1 hourly / T2 part-of-day / T3 daily) so the backtest can weight it.

CREATE TABLE IF NOT EXISTS landslide_events (
    id                   text PRIMARY KEY,
    source               text NOT NULL,
    event_time           timestamptz NOT NULL,
    temporal_accuracy    text,
    geographic_accuracy  text,
    landslide_type       text,
    region               text,
    province             text,
    municipality         text,
    elevation_m          double precision,
    slope_deg            double precision,
    duration_h           double precision,
    cumulated_rainfall_mm double precision,
    geom                 geometry(Point, 4326) NOT NULL,
    attributes           jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at           timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS landslide_events_geom_gix
    ON landslide_events USING gist (geom);

CREATE INDEX IF NOT EXISTS landslide_events_time_idx
    ON landslide_events (event_time);
