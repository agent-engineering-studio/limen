-- 080 — lo scuotimento di un terremoto, cella per cella (#284).
--
-- La componente E delle frane leggeva gli eventi di tutta Italia per ogni
-- cella, con una PGA ricavata dalla sola magnitudo: un M 3,5 in Calabria
-- avrebbe scosso anche il Trentino. Qui sta la PGA che la ShakeMap INGV stima
-- per ogni cella (dal punto di griglia più vicino al centroide), solo dove
-- supera `seismic.pga_min_g` di `landslide.yaml`: sotto, la cella non è stata
-- scossa abbastanza da contare, e la riga non serve.
--
-- Un evento senza ShakeMap non ha righe, e per E non conta: meglio nessun
-- numero che uno inventato. Cancellare un evento o una cella porta via le
-- sue righe.

CREATE TABLE IF NOT EXISTS seismic_pga_cella (
    event_id  text NOT NULL REFERENCES seismic_events(id) ON DELETE CASCADE,
    cell_id   text NOT NULL REFERENCES grid_cells(id) ON DELETE CASCADE,
    pga_g     double precision NOT NULL CHECK (pga_g >= 0),
    PRIMARY KEY (event_id, cell_id)
);

-- Lo sweep chiede gli eventi delle celle di un'AOI.
CREATE INDEX IF NOT EXISTS seismic_pga_cella_cell_idx ON seismic_pga_cella (cell_id);

-- Quando la PGA per cella di un evento è stata calcolata (anche zero celle:
-- un M 3,5 può non superare la soglia da nessuna parte). Il job riscarica la
-- ShakeMap solo se questo manca o se l'evento ha meno di un giorno: gli
-- eventi già salvati prima di questa migrazione, o dopo che si azzera la
-- colonna (soglia cambiata, regione nuova), si ricalcolano da soli.
ALTER TABLE seismic_events ADD COLUMN IF NOT EXISTS pga_celle_at timestamptz;
