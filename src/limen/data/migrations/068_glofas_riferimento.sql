-- 068 — la portata ordinaria di ogni nodo GloFAS, calcolata una volta (#200).
--
-- Il ramo fluviale divide la portata prevista di un nodo per la sua piena
-- ordinaria: il percentile della sua storia GloFAS su due anni. Tenuta in una
-- cache a 30 giorni e ricalcolata in blocco per regione, costava all'API
-- pubblica di Open-Meteo più di quanto il tetto di 10.000 chiamate al giorno
-- consenta: l'11 ottobre 2026 la pausa dopo il 429 è scattata alle 00:18 UTC,
-- e il ramo fluviale è rimasto spento in tutta Italia per il resto del giorno.
--
-- La piena ordinaria di un fiume è una proprietà del bacino, non del meteo:
-- calcolata una volta regge mesi. Qui la si conserva per nodo, la riempie un
-- passo notturno un po' alla volta, e lo sweep la legge soltanto.
--
-- `portata` NULL vuol dire «GloFAS ha risposto, ma la serie è troppo corta o
-- vuota»: non c'è un fiume da misurare. Un nodo che manca dalla tabella non è
-- ancora stato calcolato. Le due cose restano distinte, perché un 429 non
-- deve diventare «nessun fiume».
--
-- Coordinate NUMERIC come per `fwi_state`: l'uguaglianza fra float in una
-- chiave primaria aprirebbe un secondo nodo sul rumore di arrotondamento.

CREATE TABLE IF NOT EXISTS glofas_riferimento (
    node_lon     numeric(9,4)     NOT NULL,
    node_lat     numeric(9,4)     NOT NULL,
    percentile   numeric(4,3)     NOT NULL,
    window_days  integer          NOT NULL,
    portata      double precision,
    calcolato    timestamptz      NOT NULL DEFAULT now(),
    PRIMARY KEY (node_lon, node_lat, percentile, window_days)
);
