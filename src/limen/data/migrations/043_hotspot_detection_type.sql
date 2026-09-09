-- 043_hotspot_detection_type.sql
--
-- La classificazione FIRMS della detection, che stavamo buttando (#66).
--
-- FIRMS pubblica una colonna `type` che dice **cosa** ha visto il satellite:
--
--   0  incendio di vegetazione (presunto)
--   1  vulcano attivo
--   2  altra sorgente statica al suolo — impianti industriali, torce
--   3  offshore
--
-- Ignorarla ha prodotto una `fire_density` che misurava le acciaierie. La
-- cella con il valore massimo in Italia — 3.308 giorni-incendio su ~4.700
-- giorni d'archivio VIIRS, cioè il 70% delle giornate — sta a 17,210 E /
-- 40,508 N: è l'ILVA di Taranto. La seconda è un impianto lombardo, e la
-- Sicilia arrivava a 1.817 fra petrolchimico ed Etna.
--
-- Il filtro di confidenza non li toglieva e non poteva: un'acciaieria è una
-- detection ad **alta** confidenza e alta potenza radiativa. È davvero calda.
-- Solo la classificazione della fonte distingue "brucia" da "è un forno".
--
-- Sull'archivio italiano: 223.041 detection VIIRS di tipo 0 contro 68.204 di
-- tipo 2 e 10.913 di tipo 1 — un quarto del dataset non è un incendio.
--
-- Nullable: le righe NRT già ingerite non l'hanno, e non si può inventare la
-- classe di una detection passata. `fire_events` conta solo il tipo 0, quindi
-- una detection di classe ignota non diventa un evento incendio: sbagliare
-- per difetto perde qualche giorno di NRT, sbagliare per eccesso mette
-- Taranto nel truth set ogni giorno dell'anno.

ALTER TABLE fire_hotspots
    ADD COLUMN IF NOT EXISTS detection_type smallint;

COMMENT ON COLUMN fire_hotspots.detection_type IS
    'FIRMS type: 0 vegetazione, 1 vulcano, 2 sorgente statica al suolo, 3 offshore';

CREATE INDEX IF NOT EXISTS fire_hotspots_vegetation_idx
    ON fire_hotspots (acq_date DESC)
    WHERE detection_type = 0;
