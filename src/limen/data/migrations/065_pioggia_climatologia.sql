-- 065 — com'è di solito la pioggia a 72 ore, per nodo dell'alluvione.
--
-- Le soglie della pioggia dell'alluvione (40 → 120 mm in 72 h) sono uguali per
-- tutta Italia, e il clima no: a Trieste 105 mm in tre giorni capitano circa
-- una volta l'anno, a Bari mai nel decennio 2016-2025. Il 6 ottobre 2026
-- Limen dava Trieste «molto alto» mentre il bollettino regionale, tarato sul
-- clima locale, non dava allerta.
--
-- Qui sta la distribuzione delle somme di pioggia su tre giorni per ogni nodo
-- del reticolo dell'alluvione (0,1°), dall'archivio ERA5: le soglie locali
-- sono i percentili di questa distribuzione che 40 e 120 mm rappresentano
-- nella regione dove sono state tarate. `quantili` segue i livelli fissati in
-- `core/scoring/flood/climatologia.py`; NUMERIC per lo stesso motivo di
-- `fwi_state`.

CREATE TABLE IF NOT EXISTS pioggia_climatologia (
    node_lon    numeric(9,4)       NOT NULL,
    node_lat    numeric(9,4)       NOT NULL,
    giorni      integer            NOT NULL CHECK (giorni > 0),
    quantili    double precision[] NOT NULL,
    anno_da     integer            NOT NULL,
    anno_a      integer            NOT NULL,
    computed_at timestamptz        NOT NULL DEFAULT now(),
    PRIMARY KEY (node_lon, node_lat)
);
