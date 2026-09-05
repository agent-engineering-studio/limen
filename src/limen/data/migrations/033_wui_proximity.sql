-- Interfaccia urbano-foresta (WUI) per cella — issue #62.
--
-- `near_urban` dice già se una cella ha case vicino, ed è ciò che alza la
-- priorità degli alert per le frane. Per un incendio non basta: un isolato
-- circondato da altri isolati non brucia, uno che confina con il bosco sì.
-- La distinzione è la vegetazione adiacente, e vale solo per il fuoco.
--
-- Normalizzato in [0,1]: 1 sulla cella di interfaccia, decrescente con la
-- distanza fino ad annullarsi oltre il raggio configurato. NULL = ignoto,
-- che è diverso da 0 (= lontano da qualunque interfaccia) e va tenuto
-- distinto: senza CORINE la colonna resta NULL e il termine si spegne.

ALTER TABLE cell_static_factors
    ADD COLUMN IF NOT EXISTS wui_proximity_norm DOUBLE PRECISION
        CHECK (wui_proximity_norm IS NULL
               OR (wui_proximity_norm >= 0 AND wui_proximity_norm <= 1));

COMMENT ON COLUMN cell_static_factors.wui_proximity_norm IS
    'Prossimità all''interfaccia urbano-vegetazione in [0,1] (#62). NULL '
    'finché CORINE non popola landuse_code: assente non è zero.';
