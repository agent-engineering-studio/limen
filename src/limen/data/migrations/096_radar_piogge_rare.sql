-- 096 — Le piogge rare viste dal radar DPC, una notte alla volta (#643).
--
-- Il passo notturno `piogge_rare` legge dall'archivio del «Merging» (#240) le
-- 24 ore del giorno prima di solo radar (SRT1), cerca dove la pioggia ha
-- passato il livello che quel posto vede una volta in dieci anni
-- (`dpc_radar.rare_events`, climatologia 2018-2025) e confronta ogni evento
-- con il «Merging» degli stessi blocchi (`with_merging`): un evento che i
-- pluviometri non vedono è con buona probabilità un'eco, non pioggia.
--
-- Sono **candidati**, non eventi verificati: la raccolta dalla stampa (#347)
-- li usa per una ricerca mirata sul comune, e solo due testate fanno un
-- evento in `verifiche_eventi`. Non entrano in nessun punteggio.

CREATE TABLE IF NOT EXISTS radar_piogge_rare (
    evento_at       timestamptz      NOT NULL,   -- fine della finestra più rara
    finestra_ore    integer          NOT NULL,   -- 1, 3, 6 o 24
    lon             double precision NOT NULL,
    lat             double precision NOT NULL,
    mm              double precision NOT NULL,   -- solo radar, nella finestra
    livello_mm      double precision NOT NULL,   -- il livello dei dieci anni lì
    ritorno_anni    double precision NOT NULL,   -- tetto 50
    primo_at        timestamptz      NOT NULL,
    ultimo_at       timestamptz      NOT NULL,
    area_km2        double precision NOT NULL,
    bbox            double precision[] NOT NULL, -- ovest, sud, est, nord
    radar_mm        double precision,            -- dopo with_merging; NULL = archivio incompleto
    merging_mm      double precision,
    confermato      boolean,                     -- NULL = non si sa
    istat_code      text,                        -- il comune del punto più raro
    trovato_at      timestamptz      NOT NULL DEFAULT now(),
    PRIMARY KEY (evento_at, lon, lat)
);
CREATE INDEX IF NOT EXISTS radar_piogge_rare_evento_idx ON radar_piogge_rare (evento_at);
