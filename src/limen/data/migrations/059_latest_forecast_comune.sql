-- 059 — la previsione per comune, per ogni pericolo, **anche quando è bassa**.
--
-- `latest_forecast` (057) tiene solo le celle da Moderato in su: una regola
-- nata per contenere lo storico, dove ogni cella sotto soglia sarebbe stata
-- una riga in più a ogni corsa. Per il grafico del comune è la regola
-- sbagliata. Il 30 settembre la previsione d'alluvione è girata su tutte le
-- venti regioni ed è uscita sotto soglia ovunque: zero righe, e nel grafico
-- nessun tratteggio — come se la previsione non ci fosse. «Previsto 0,00» è
-- una previsione, ed è quella che chi guarda il cielo asciutto si aspetta.
--
-- Una riga per (comune, pericolo, orizzonte), sempre: il massimo sulle celle
-- del comune e la sua classe. Sono ~71.000 righe per i 7.901 comuni, contro i
-- milioni che servirebbero tenendo tutte le celle. Per l'alluvione anche la
-- pioggia prevista più alta, perché sotto i 40 mm il punteggio resta zero e
-- il numero che dice quanto manca è quello.

CREATE TABLE IF NOT EXISTS latest_forecast_comune (
    istat_code  text        NOT NULL,
    hazard_type hazard_type NOT NULL,
    horizon_h   integer     NOT NULL,
    score       double precision NOT NULL,
    class       text        NOT NULL,
    -- Solo alluvione: la pioggia prevista a 72 ore più alta fra le celle.
    rain_mm     double precision,
    run_at      timestamptz NOT NULL,
    target_at   timestamptz NOT NULL,
    PRIMARY KEY (istat_code, hazard_type, horizon_h)
);
