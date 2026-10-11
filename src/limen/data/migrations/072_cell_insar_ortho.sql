-- 072 — EGMS Ortho L3 per cella: le due componenti, non un numero solo.
--
-- `cell_insar_features` (010) era pensata per i punti PS di un'API EGMS che
-- non esiste; il portale serve tile da 100 km con la velocità media su una
-- griglia di 100 m, in due componenti: verticale e est-ovest. Servono tutte e
-- due, separate: un versante in frana si muove soprattutto in orizzontale,
-- una pianura che subside soprattutto in verticale, e il modulo da solo non
-- le distingue.
--
-- Con il prodotto Ortho le colonne di 010 diventano:
--   insar_velocity_mmy — 90° percentile del modulo sqrt(E² + U²) sui pixel
--                        della cella (mm/anno): pochi pixel in movimento in
--                        una cella da 1 km sono il segnale, la mediana li
--                        cancellerebbe;
--   insar_accel_mmy2   — NULL: il GeoTIFF porta solo la velocità media;
--   scatterer_count    — pixel da 100 m con entrambe le componenti valide
--                        (0-100): 0 vuol dire «non misurato», non «fermo».

ALTER TABLE cell_insar_features
    ADD COLUMN IF NOT EXISTS velocita_verticale_mmy double precision,
    ADD COLUMN IF NOT EXISTS velocita_est_mmy       double precision;
