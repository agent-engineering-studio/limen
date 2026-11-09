-- 090 — #466: le colonne di cell_static_factors che nessun passo riempie.
--
-- Misura del 2026-11-08: NULL su tutte le 312.550 celle, e nessun codice le
-- legge. Facevano credere a chi legge lo schema che il dato esistesse.
--
-- * population_count, buildings_count, infra_density_norm (migrazione 008):
--   l'esposizione è exposure_norm, dai residenti ISPRA in aree a pericolo;
-- * land_cover (002): il passo CORINE scrive landuse_code, e il nome della
--   classe sta in config/corine_classi.yaml.
--
-- Restano twi (feature dello sfidante ML, da misurare prima di calcolarla) e
-- dist_faults_m (la riempie il passo geologico con LIMEN_FAULTS_SHAPEFILE).
-- DROP COLUMN su PostgreSQL tocca solo il catalogo: nessuna riscrittura.

ALTER TABLE cell_static_factors
    DROP COLUMN IF EXISTS population_count,
    DROP COLUMN IF EXISTS buildings_count,
    DROP COLUMN IF EXISTS infra_density_norm,
    DROP COLUMN IF EXISTS land_cover;
