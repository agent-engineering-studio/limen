-- 042_fire_history.sql
--
-- Storia del fuoco per cella (#66): eventi datati e densità statica.
--
-- `fire_hotspots` è un feed di *detection*: un singolo rogo produce decine di
-- pixel caldi, visti da più satelliti e più orbite nello stesso giorno.
-- Contarli come eventi darebbe alla cella con un incendio ben osservato la
-- densità di dieci incendi.
--
-- `fire_events` è la deduplica: **una riga per cella e per giorno**. Non
-- serve un DBSCAN, e questa è una scelta, non una scorciatoia — la
-- risoluzione a cui il resto del sistema lavora *è* la cella da 1 km e il
-- giorno, quindi raggruppare a scala più fine con un raggio e una soglia
-- introdurrebbe due parametri per poi ri-aggregare esattamente qui. Il
-- raggruppamento per (cella, giorno) è inoltre deterministico per
-- costruzione, mentre un DBSCAN dipende dall'ordine di visita sui punti di
-- confine.
--
-- Un incendio che brucia tre giorni resta tre eventi sulla stessa cella: per
-- il rischio è la cosa giusta, perché tre giorni di fuoco sono tre giorni in
-- cui quella cella era in pericolo.
--
-- **FIRMS è presence-only.** L'assenza di un evento non è la prova che non
-- sia bruciato: nuvole, chioma e roghi sotto la soglia di rilevamento non
-- compaiono. Chi userà questa tabella come etichetta deve campionare le
-- pseudo-assenze (lo stesso caso-controllo del training frane), non leggere
-- lo zero come "qui non brucia".

CREATE TABLE IF NOT EXISTS fire_events (
    cell_id     text NOT NULL REFERENCES grid_cells(id) ON DELETE CASCADE,
    event_date  date NOT NULL,
    hotspots    integer NOT NULL,
    sources     text[]  NOT NULL,
    max_frp_mw  double precision,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (cell_id, event_date)
);

CREATE INDEX IF NOT EXISTS fire_events_date_idx ON fire_events (event_date DESC);

-- Densità storica del fuoco per cella: quanti giorni-incendio distinti ha
-- avuto. Le celle sono di 1 km², quindi il conteggio *è* la densità per km².
--
-- `NOT NULL DEFAULT 0` e non NULL: qui lo zero è un'informazione — nessun
-- hotspot è stato rilevato su quella cella — mentre NULL significherebbe "il
-- layer non è stato caricato", che è la condizione di `slope_deg` e
-- `landuse_code`. Le due cose non vanno confuse, ed è per questo che la
-- colonna nasce popolata invece di aspettare il bootstrap.
ALTER TABLE cell_static_factors
    ADD COLUMN IF NOT EXISTS fire_density integer NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS cell_static_factors_fire_density_idx
    ON cell_static_factors (fire_density)
    WHERE fire_density > 0;
