-- 041_flood_observation_masks.sql
--
-- Dove il satellite ha guardato, e quando (#64).
--
-- Serve a distinguere un falso allarme da un allarme **non verificabile**, ed
-- è la differenza fra un FAR leggibile e un numero senza senso. Misurato sul
-- Piemonte, aprile 2025: il motore ha prodotto 10.021 episodi di allerta e il
-- truth set conteneva 12 celle allagate, perché EMSR800 ha mappato 0,3 km².
-- Chiamare falsi quei 10.009 episodi vorrebbe dire dichiarare asciutto tutto
-- ciò che nessuno ha osservato.
--
-- Dentro la maschera l'analista ha delineato l'allagamento, quindi l'assenza
-- di un poligono è un "non allagato" osservato. Fuori non c'è informazione:
-- quegli episodi escono dal denominatore, come `non verificabile` esce dal
-- denominatore nel protocollo FAR degli alert (#59).
--
-- La geometria arriva da `aois[].extent` del dettaglio dell'attivazione, non
-- dai pacchetti prodotti: verificato su EMSR762 AOI01 che coincide con
-- l'`areaOfInterestA` dello shapefile (1846,1 km² entrambe, sovrapposizione
-- 100%), e costa una chiamata invece di 100 MB di scarico.
--
-- `observed_time` è per prodotto e non per attivazione: una AOI monitorata
-- due volte è stata osservata due volte, e un'allerta è verificabile solo
-- rispetto a un passaggio che è venuto **dopo** di essa.

CREATE TABLE IF NOT EXISTS flood_observation_masks (
    id              text PRIMARY KEY,
    source          text NOT NULL,
    activation_code text NOT NULL,
    aoi_label       text NOT NULL,
    product_type    text,
    observed_time   timestamptz NOT NULL,
    area_km2        double precision,
    geom            geometry(MultiPolygon, 4326) NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS flood_observation_masks_geom_gix
    ON flood_observation_masks USING gist (geom);

CREATE INDEX IF NOT EXISTS flood_observation_masks_time_idx
    ON flood_observation_masks (observed_time);
