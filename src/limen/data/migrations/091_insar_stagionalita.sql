-- 091 — EGMS per cella: accelerazione e stagionalità dal CSV L3 (#380).
--
-- Il GeoTIFF Ortho L3 porta solo la velocità media; il CSV nello stesso ZIP
-- ha per ogni pixel da 100 m anche il modello che EGMS adatta alla serie:
-- `acceleration` (mm/anno²) e `seasonality` (ampiezza del ciclo annuale, mm).
-- Con questa migrazione:
--   insar_accel_mmy2          — non più NULL: 90° percentile del modulo
--                               sqrt(aE² + aU²) sui pixel della cella, come la
--                               velocità (un versante che accelera occupa pochi
--                               pixel, la mediana lo cancellerebbe);
--   stagionalita_verticale_mm — mediana dell'ampiezza stagionale della
--                               componente verticale: argille che si gonfiano e
--                               si ritirano, falde che salgono e scendono.

ALTER TABLE cell_insar_features
    ADD COLUMN IF NOT EXISTS stagionalita_verticale_mm double precision;
