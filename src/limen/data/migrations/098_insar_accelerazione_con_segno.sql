-- 098 — EGMS per cella: accelerazione verticale con segno, coda della
-- velocità verticale e copertura (#700).
--
-- `insar_accel_mmy2` era il 90° percentile del modulo sqrt(aE² + aU²): sempre
-- positivo, non distingue un versante che accelera da uno che rallenta, e alle
-- Murge, che sono ferme, vale 1,24 mm/anno² nella cella mediana. Dal calcolo
-- `ortho-l3-v3` non si scrive più (resta NULL) e al suo posto, sugli stessi
-- pixel della velocità (`egms_client.cells.per_cell`):
--   accelerazione_verticale_mmy2     — mediana dell'accelerazione verticale;
--   accelerazione_verticale_p10_mmy2 — 10° percentile: negativo se alcuni
--                                      pixel scendono sempre più in fretta;
--   velocita_verticale_p10_mmy       — 10° percentile della velocità
--                                      verticale: i pixel che scendono di più;
--   copertura                        — pixel con un valore sui pixel della
--                                      cella, fra 0 e 1.

ALTER TABLE cell_insar_features
    ADD COLUMN IF NOT EXISTS accelerazione_verticale_mmy2 double precision,
    ADD COLUMN IF NOT EXISTS accelerazione_verticale_p10_mmy2 double precision,
    ADD COLUMN IF NOT EXISTS velocita_verticale_p10_mmy double precision,
    ADD COLUMN IF NOT EXISTS copertura double precision;

COMMENT ON COLUMN cell_insar_features.scatterer_count IS
    'Pixel da 100 m della griglia Ortho L3 con un valore in tutte e due le componenti, non bersagli radar. 0 = il satellite qui non vede.';
COMMENT ON COLUMN cell_insar_features.insar_accel_mmy2 IS
    'Modulo p90 dell''accelerazione (calcolo ortho-l3-v2). Dal v3 resta NULL: vedi accelerazione_verticale_mmy2.';
COMMENT ON COLUMN cell_insar_features.period_start IS
    'Prima acquisizione della release (egms_client.releases.window), non il 1° gennaio del suo nome. NULL se non è nota.';
