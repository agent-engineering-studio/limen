-- 038_pai_hazard_subdiv.sql
--
-- Compagno lato query di `pai_hazard`, gemello di `flood_hazard_subdiv`
-- (migrazione 014). Stessa patologia, stessa cura.
--
-- La mosaicatura PAI frana nazionale ha 928.540 poligoni da 125 vertici in
-- media, ma **36 sopra i 100.000 vertici** e il peggiore a 1.321.715. Il
-- bounding box di quei mostri copre migliaia di celle, quindi l'indice GiST
-- li restituisce come candidati per ognuna e il test esatto di
-- `ST_Intersects` va rifatto per intero ogni volta. Misurato su 200 celle
-- della Toscana:
--
--     LEFT JOIN pai_hazard            5.878 ms
--     LEFT JOIN flood_hazard_subdiv     133 ms   (stesse celle, tabella già suddivisa)
--
-- Su 23.779 celle sono ~700 s, che con la variabilità fra zone dense e rade
-- sfonda il timeout di 900 s: è così che `make flood-data` è morto sulla
-- Toscana dopo aver completato 15 regioni su 20.
--
-- Qui ogni poligono sorgente è spezzato da ST_Subdivide in parti piccole:
-- l'indice torna selettivo e i test esatti tornano a costare poco.
-- `pai_repo.upsert_many` tiene questa tabella in passo con `pai_hazard`;
-- `bootstrap-static` sana le righe sincronizzate prima che esistesse.
-- `pai_hazard` resta la sorgente autoritativa.

CREATE TABLE IF NOT EXISTS pai_hazard_subdiv (
    id                 text NOT NULL,
    hazard_class       text NOT NULL,
    hazard_class_norm  double precision,
    geom               geometry(Polygon, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS pai_hazard_subdiv_geom_gix
    ON pai_hazard_subdiv USING GIST (geom);
CREATE INDEX IF NOT EXISTS pai_hazard_subdiv_id_ix
    ON pai_hazard_subdiv (id);
