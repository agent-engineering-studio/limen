-- 040_flood_events.sql
--
-- Catalogo datato di eventi alluvionali: il truth set del backtest flood
-- (#64), come `landslide_events` lo è per le frane.
--
-- Distinto da `flood_hazard` (mosaico idraulico ISPRA), che è una mappa di
-- *pericolosità* — dove l'acqua può arrivare, senza data. Qui ci sono
-- allagamenti realmente accaduti, con un istante e un perimetro.
--
-- La geometria è l'**estensione osservata** dei prodotti di delineazione
-- Copernicus EMS, non l'area di interesse della mappatura: per EMSR762 le
-- due differiscono di due ordini di grandezza (1,19 km² allagati dentro una
-- AOI di ~750 km²), e prendere l'AOI per verità significherebbe dichiarare
-- allagate centinaia di celle asciutte.
--
-- Due tempi distinti, perché rispondono a domande diverse:
--   * `event_time`   — inizio dell'evento secondo l'attivazione. È l'ancora
--     del backtest: la domanda è se la cella era in allerta *prima* che
--     l'acqua arrivasse.
--   * `observed_time`— acquisizione dell'immagine da cui è stato tracciato il
--     perimetro. Usarla come ancora conterebbe come "preavviso" ore in cui
--     l'allagamento era già in corso.

CREATE TABLE IF NOT EXISTS flood_events (
    id               text PRIMARY KEY,
    source           text NOT NULL,
    activation_code  text,
    aoi_label        text,
    event_time       timestamptz NOT NULL,
    observed_time    timestamptz,
    event_type       text,
    detection_method text,
    area_km2         double precision,
    geom             geometry(MultiPolygon, 4326) NOT NULL,
    attributes       jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS flood_events_geom_gix
    ON flood_events USING gist (geom);

CREATE INDEX IF NOT EXISTS flood_events_time_idx
    ON flood_events (event_time);

CREATE INDEX IF NOT EXISTS flood_events_activation_idx
    ON flood_events (activation_code);
