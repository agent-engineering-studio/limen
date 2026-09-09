-- 044_perimeter_fire_severity.sql
--
-- Severità del bruciato da FRP FIRMS (#67).
--
-- Il fattore F post-incendio delle frane è una campana sul **solo tempo**:
-- un incendio di chioma severo e una bruciatura di stoppie pesano uguale. Il
-- dNBR sarebbe la misura giusta, ma `EffisClient.fetch_dnbr` è uno stub —
-- l'endpoint Copernicus richiede una richiesta manuale. La potenza radiativa
-- degli hotspot FIRMS è un proxy gratuito e automatico.
--
-- **Si salva la misura, non la severità normalizzata.** La colonna porta la
-- somma di FRP e il conteggio degli hotspot; la normalizzazione a [0,1] vive
-- in `post_fire.frp_*` nello YAML ed è una funzione pura. Salvare il valore
-- normalizzato legherebbe una taratura a una ri-ingestione: cambiare una
-- soglia nello YAML dovrebbe bastare, come per ogni altro parametro del
-- motore.
--
-- **`frp_density_mw_per_ha` e non la sola somma.** La somma di FRP scala con
-- la *dimensione* dell'incendio, non con la sua intensità: un incendio di
-- 4.000 ha a bassa severità somma più di uno di 100 ha di chioma. Ma per
-- amplificare il rischio frana su una cella conta quanto duramente **quella**
-- area ha bruciato, che è ciò che misura il dNBR. La densità è la somma
-- divisa per l'area del perimetro, quindi un'intensità media.
--
-- La somma resta salvata accanto: serve a mostrare che le due grandezze
-- rispondono a domande diverse, ed è il numero che la letteratura lega alla
-- biomassa consumata (Wooster).

ALTER TABLE fire_perimeters
    ADD COLUMN IF NOT EXISTS frp_sum_mw double precision,
    ADD COLUMN IF NOT EXISTS frp_hotspots integer,
    ADD COLUMN IF NOT EXISTS frp_density_mw_per_ha double precision;

COMMENT ON COLUMN fire_perimeters.frp_sum_mw IS
    'Somma della potenza radiativa degli hotspot di vegetazione dentro il perimetro, entro la finestra dalla firedate';
COMMENT ON COLUMN fire_perimeters.frp_density_mw_per_ha IS
    'frp_sum_mw / area_ha: intensità media, indipendente dalla dimensione del rogo';

CREATE INDEX IF NOT EXISTS fire_perimeters_frp_density_idx
    ON fire_perimeters (frp_density_mw_per_ha)
    WHERE frp_density_mw_per_ha IS NOT NULL;
