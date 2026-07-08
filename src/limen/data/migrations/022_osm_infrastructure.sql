-- Rete infrastrutturale OSM (Geofabrik, © OpenStreetMap contributors,
-- ODbL): strade principali (motorway/trunk/primary/secondary) e ferrovie.
-- Il CORINE 122 copre solo 43 celle in Italia — troppo rado per stimare
-- l'esposizione viabilità; la rete OSM completa dà una distanza reale
-- per cella. Caricata da `limen bootstrap-static` quando
-- LIMEN_OSM_ROADS / LIMEN_OSM_RAILWAYS puntano agli estratti vettoriali.

CREATE TABLE IF NOT EXISTS osm_infrastructure (
    id      bigserial PRIMARY KEY,
    kind    text NOT NULL CHECK (kind IN ('road', 'rail')),
    class   text,
    geom    geometry(LineString, 4326) NOT NULL
);

-- Indici GiST parziali per kind: il KNN `<->` del bootstrap filtra sempre
-- su un solo kind, e un indice parziale garantisce l'index scan.
CREATE INDEX IF NOT EXISTS osm_infrastructure_road_gix
    ON osm_infrastructure USING gist (geom) WHERE kind = 'road';
CREATE INDEX IF NOT EXISTS osm_infrastructure_rail_gix
    ON osm_infrastructure USING gist (geom) WHERE kind = 'rail';

-- Distanza (m, cap 50 km) dal centroide cella alla rete più vicina.
-- NULL finché la rete OSM non viene ingerita: il fattore esposizione
-- degrada ai flag CORINE esistenti (near_infra).
ALTER TABLE cell_static_factors
    ADD COLUMN IF NOT EXISTS distance_to_road_m double precision,
    ADD COLUMN IF NOT EXISTS distance_to_rail_m double precision,
    ADD COLUMN IF NOT EXISTS nearest_road_class text;
