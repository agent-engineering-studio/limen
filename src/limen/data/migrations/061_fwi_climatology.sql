-- 061 — com'è di solito l'indice incendi, per nodo e per mese.
--
-- Le classi dell'incendio sono soglie assolute dell'FWI, le stesse di
-- Copernicus EFFIS: FWI 36 è «High» ad agosto come a ottobre. È la stessa
-- scala ufficiale, ma non dice **rispetto al solito**: a Montegiordano, il 2
-- ottobre 2026, FWI 36 in un ottobre mite e senza pioggia si leggeva come un
-- allarme, mentre ad agosto in Calabria lo stesso numero è la norma.
--
-- Qui sta la distribuzione dell'FWI per (nodo, mese) su più anni di archivio,
-- calcolata da `limen fwi-climatology` con la stessa catena e la stessa
-- lettura di mezzogiorno del calcolo operativo. I nodi sono quelli di
-- `fwi_state` (reticolo globale, NUMERIC per lo stesso motivo: l'uguaglianza
-- fra float in una chiave apre un secondo nodo per rumore di arrotondamento).
--
-- `quantiles` sono 21 valori, dal minimo al massimo a passi del 5 %: abbastanza
-- per dire a che percentile cade un valore senza tenere ogni giorno.

CREATE TABLE IF NOT EXISTS fwi_climatology (
    node_lon    numeric(9,4) NOT NULL,
    node_lat    numeric(9,4) NOT NULL,
    month       smallint     NOT NULL CHECK (month BETWEEN 1 AND 12),
    days        integer      NOT NULL CHECK (days > 0),
    quantiles   double precision[] NOT NULL CHECK (cardinality(quantiles) = 21),
    year_from   integer      NOT NULL,
    year_to     integer      NOT NULL,
    computed_at timestamptz  NOT NULL DEFAULT now(),
    PRIMARY KEY (node_lon, node_lat, month)
);

COMMENT ON TABLE fwi_climatology IS
    'Distribuzione dell''FWI per nodo e mese (21 quantili, 0..100 a passi del 5 %), '
    'da `limen fwi-climatology` sull''archivio ERA5. Informativa: non entra nel punteggio.';
