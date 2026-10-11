-- 071 — la previsione GloFAS per nodo, scaricata dall'EWDS.
--
-- Il ramo fluviale divide il picco di portata previsto nei prossimi sette
-- giorni per la piena ordinaria del nodo (`glofas_riferimento`, 068). Il
-- picco lo chiedeva all'API pubblica di Open-Meteo, che ha un tetto di 10.000
-- chiamate al giorno e dopo un 429 tace fino alla mezzanotte UTC. Lo stesso
-- dato è nell'Early Warning Data Store di Copernicus, a griglia: una corsa
-- sull'Italia è un file da ~400 KB, scaricato una volta al giorno.
--
-- Una riga per nodo e corsa. Un nodo assente in una corsa non ha previsione
-- (cella mascherata o fuori riquadro): non è un fiume basso.

CREATE TABLE IF NOT EXISTS glofas_previsione (
    node_lon   numeric(9,4)     NOT NULL,
    node_lat   numeric(9,4)     NOT NULL,
    corsa      date             NOT NULL,
    picco      double precision NOT NULL,
    fonte      text             NOT NULL,
    scaricato  timestamptz      NOT NULL DEFAULT now(),
    PRIMARY KEY (node_lon, node_lat, corsa)
);

CREATE INDEX IF NOT EXISTS glofas_previsione_corsa_idx ON glofas_previsione (corsa);
