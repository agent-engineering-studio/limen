-- 092 — Le soglie GloFAS v4 dei periodi di ritorno per nodo (#522).
--
-- La portata con tempo di ritorno di 2, 5 e 20 anni nella cella GloFAS che
-- il nodo legge (la stessa di `glofas_riferimento`: quella che Open-Meteo
-- serve, un passo a est della dichiarata). Sono i file ufficiali di GloFAS
-- (wiki ECMWF, «GloFAS auxiliary data»), non un adattamento nostro.
--
-- Servono a un'**etichetta**, non al punteggio: la misura dell'8 novembre
-- 2026 ha dato AUC 0,952 contro 0,953 del q90, quindi il ramo fluviale resta
-- sul q90 e il riquadro della cella dice in più «sopra la piena da 5 anni»,
-- che un sindaco legge e «1,6 volte il q90 del nodo» no.
--
-- NULL = la cella GloFAS non ha soglia (mascherata: niente fiume lì).

CREATE TABLE IF NOT EXISTS glofas_soglie (
    node_lon  numeric(9,4)     NOT NULL,
    node_lat  numeric(9,4)     NOT NULL,
    rl2       double precision,
    rl5       double precision,
    rl20      double precision,
    fonte     text             NOT NULL,
    calcolato timestamptz      NOT NULL DEFAULT now(),
    PRIMARY KEY (node_lon, node_lat)
);
