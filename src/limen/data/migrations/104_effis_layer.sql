-- 104 — il layer EFFIS di ogni perimetro, e il layer che Limen legge.
--
-- EFFIS pubblica le aree bruciate in due layer che non contano gli stessi
-- incendi (effis-client 0.3.0, misura del 2026-11-28):
--
--   * `nrt.ba.poly` (/gwis): dal 2012, il più piccolo di 73 ha nel riquadro
--     della Basilicata; conta anche calore che non è vegetazione bruciata
--     (255 «aree bruciate» sulla cima dell'Etna, 135.917 ha);
--   * `ms:modis.ba.poly` (/effis): dal 2016, fino a un ettaro, con il Comune,
--     l'uso del suolo bruciato e la data dell'ultima revisione.
--
-- Fino a qui `effis-sync` leggeva il primo. Da qui legge il secondo
-- (decisione del 2026-11-28). Le righe dei due layer non stanno mai nella
-- tabella senza il nome del layer:
--
--   * `layer` su ogni riga; quelle già presenti vengono dal primo e restano,
--     marcate `nrt.ba.poly`. Nessuna riga si cancella qui: toglierle è un
--     passo a parte, da approvare.
--   * La chiave diventa (layer, id): gli id dei due layer sono numeri della
--     stessa forma e possono coincidere.
--   * `layer` non ha un valore di default: chi scrive deve dirlo.
--
-- Chi legge legge la vista `v_fire_perimeters`, che tiene solo il layer di
-- Limen: il backtest incendio, la severità post-incendio, il controllo con
-- FIRMS, le misure e la mappa. Cambiare layer è cambiare questa vista.

ALTER TABLE fire_perimeters ADD COLUMN IF NOT EXISTS layer text;
UPDATE fire_perimeters SET layer = 'nrt.ba.poly' WHERE layer IS NULL;
ALTER TABLE fire_perimeters ALTER COLUMN layer SET NOT NULL;
ALTER TABLE fire_perimeters
    ADD CONSTRAINT fire_perimeters_layer_check
    CHECK (layer IN ('nrt.ba.poly', 'ms:modis.ba.poly'));

ALTER TABLE fire_perimeters DROP CONSTRAINT fire_perimeters_pkey;
ALTER TABLE fire_perimeters ADD PRIMARY KEY (layer, id);

-- Quello che solo `ms:modis.ba.poly` dice. NULL sulle righe di `nrt.ba.poly`.
ALTER TABLE fire_perimeters
    ADD COLUMN IF NOT EXISTS municipality text,
    ADD COLUMN IF NOT EXISTS final_date date,
    ADD COLUMN IF NOT EXISTS last_update date,
    ADD COLUMN IF NOT EXISTS land_cover_pct jsonb,
    ADD COLUMN IF NOT EXISTS natura2000_pct double precision;

COMMENT ON COLUMN fire_perimeters.layer IS
    'Il layer EFFIS da cui viene la riga: nrt.ba.poly o ms:modis.ba.poly. Mai mescolare i due.';
COMMENT ON COLUMN fire_perimeters.municipality IS
    'Il Comune a cui EFFIS assegna l''incendio (COMMUNE), solo ms:modis.ba.poly.';
COMMENT ON COLUMN fire_perimeters.last_update IS
    'Il giorno dell''ultima revisione EFFIS della riga: un perimetro può ancora cambiare.';
COMMENT ON COLUMN fire_perimeters.land_cover_pct IS
    'Percento dell''area bruciata per uso del suolo, come lo dichiara EFFIS.';

CREATE INDEX IF NOT EXISTS fire_perimeters_layer_date_idx
    ON fire_perimeters (layer, fire_date DESC);

CREATE VIEW v_fire_perimeters AS
    SELECT * FROM fire_perimeters WHERE layer = 'ms:modis.ba.poly';

COMMENT ON VIEW v_fire_perimeters IS
    'I perimetri del layer che Limen legge (ms:modis.ba.poly). Tutti i lettori passano di qui.';

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'limen_tiles') THEN
        -- La mappa vede solo la vista: con la tabella mostrerebbe i due layer insieme.
        GRANT SELECT ON public.v_fire_perimeters TO limen_tiles;
        REVOKE SELECT ON public.fire_perimeters FROM limen_tiles;
    END IF;
END $$;
