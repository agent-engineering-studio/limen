-- 062 — previsioni di pioggia di più modelli, con il loro anticipo, e la
-- pioggia caduta: il materiale per un correttore multi-modello.
--
-- Il 6 ottobre 2026, su Trieste, la pioggia prevista in 72 ore andava da 29 mm
-- (GFS) a 108 mm (ICON) secondo il modello: l'alluvione si calcola su un
-- numero solo, e la forbice non si vedeva. Un correttore impara dai casi
-- passati quanto pesare ciascun modello e quanto è larga l'incertezza.
--
-- `rain_ens_forecast`: per (nodo, giorno, modello, anticipo) la pioggia del
-- giorno prevista `lead` giorni prima — dall'API pubblica «previous runs»,
-- l'unica che conserva le corse con il loro anticipo (la nostra istanza ha
-- solo la corsa più recente). `rain_ens_observed`: la pioggia caduta, dalla
-- rianalisi ERA5 dell'istanza propria. Nodi in NUMERIC come `fwi_state`.

CREATE TABLE IF NOT EXISTS rain_ens_forecast (
    node_lon numeric(9,4) NOT NULL,
    node_lat numeric(9,4) NOT NULL,
    day      date         NOT NULL,
    model    text         NOT NULL,
    lead     smallint     NOT NULL CHECK (lead BETWEEN 0 AND 7),
    mm       double precision NOT NULL CHECK (mm >= 0),
    PRIMARY KEY (node_lon, node_lat, day, model, lead)
);

CREATE TABLE IF NOT EXISTS rain_ens_observed (
    node_lon numeric(9,4) NOT NULL,
    node_lat numeric(9,4) NOT NULL,
    day      date         NOT NULL,
    mm       double precision NOT NULL CHECK (mm >= 0),
    PRIMARY KEY (node_lon, node_lat, day)
);
