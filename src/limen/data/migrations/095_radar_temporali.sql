-- 095 — I temporali dell'ultimo fotogramma SRI del radar DPC (#643).
--
-- La sveglia radar (`nowcast_monitoring`, ogni NOWCAST__INTERVAL_MINUTES)
-- trova sul fotogramma più recente le macchie di pioggia sopra la sua soglia
-- (`dpc_radar.storms`) e il loro moto (`dpc_radar.nowcast.motion`, dagli SRI
-- dell'ultima mezz'ora) e le scrive qui; l'API le legge senza chiedere niente
-- al servizio del DPC, che ha un tetto di richieste dichiarato (#627).
--
-- È lo stato di adesso, come `latest_risk`: ogni giro sostituisce le righe del
-- giro prima. Non entra in nessun punteggio.

CREATE TABLE IF NOT EXISTS radar_temporali (
    osservato_at     timestamptz      NOT NULL,   -- istante del fotogramma SRI
    n                integer          NOT NULL,   -- 0 = il più forte
    soglia_mmh       double precision NOT NULL,
    lon              double precision NOT NULL,   -- centro della pioggia (pesato)
    lat              double precision NOT NULL,
    area_km2         double precision NOT NULL,
    picco_mmh        double precision NOT NULL,
    media_mmh        double precision NOT NULL,
    picco_lon        double precision NOT NULL,
    picco_lat        double precision NOT NULL,
    bbox             double precision[] NOT NULL, -- ovest, sud, est, nord
    velocita_kmh     double precision,            -- NULL = moto non trovato
    direzione_gradi  double precision,            -- verso cui va, da nord
    PRIMARY KEY (osservato_at, n)
);
