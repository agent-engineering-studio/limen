-- Stato ricorsivo della catena FWI, per nodo meteo e per giorno (issue #61).
--
-- I tre codici di umidità di Van Wagner sono ricorsivi: il valore di oggi è
-- funzione di quello di ieri. Partiti dai valori standard servono settimane
-- prima che significhino qualcosa, quindi lo stato DEVE sopravvivere ai
-- riavvii del processo: è l'unica ragione per cui questa tabella esiste.
--
-- **Chiave per nodo, non per cella.** La catena dipende solo dal meteo, e
-- Open-Meteo lo dà a ~9 km: le ~26k celle di una regione condividono poche
-- decine di nodi e produrrebbero altrettante copie identiche degli stessi sei
-- numeri, ogni giorno. Il nodo è l'unità fisica del calcolo; la cella entra
-- dopo, quando combustibile e pendenza modulano l'indice.
--
-- Le coordinate sono NUMERIC e non DOUBLE PRECISION perché sono una chiave:
-- l'uguaglianza fra float è esattamente ciò che non si vuole in una PK.
-- La griglia è riproducibile finché la spaziatura resta quella dichiarata in
-- `wildfire.yaml` (fwi.node_spacing_deg); cambiarla riparte da capo, ed è il
-- motivo per cui vive in configurazione e non in una variabile d'ambiente.
--
-- Non è partizionata come `risk_assessments`: è una riga per nodo per giorno,
-- non una per sweep oraria, e soprattutto la retention non può eliminarla —
-- cancellare il giorno precedente spezzerebbe la ricorsione.

CREATE TABLE IF NOT EXISTS fwi_state (
    node_lon    NUMERIC(9, 4) NOT NULL,
    node_lat    NUMERIC(9, 4) NOT NULL,
    day         DATE          NOT NULL,

    -- I tre codici ricorsivi.
    ffmc        DOUBLE PRECISION NOT NULL CHECK (ffmc >= 0 AND ffmc <= 101),
    dmc         DOUBLE PRECISION NOT NULL CHECK (dmc >= 0),
    dc          DOUBLE PRECISION NOT NULL CHECK (dc  >= 0),

    -- I tre indici derivati. Ricalcolabili dai codici, ma conservati: sono
    -- ciò che un operatore confronta con il bollettino EFFIS, e ricalcolarli
    -- richiederebbe di nuovo il vento del giorno.
    isi         DOUBLE PRECISION NOT NULL CHECK (isi >= 0),
    bui         DOUBLE PRECISION NOT NULL CHECK (bui >= 0),
    fwi         DOUBLE PRECISION NOT NULL CHECK (fwi >= 0),

    -- Giorni consecutivi di catena alle spalle di questa riga. Il motore lo
    -- legge per dichiarare lo spin-up: un FWI calcolato su tre giorni di
    -- storia non è sbagliato, è solo non ancora significativo, e la
    -- differenza va detta invece che nascosta.
    chain_days  INTEGER       NOT NULL DEFAULT 0 CHECK (chain_days >= 0),

    -- Le quattro letture di mezzogiorno che hanno prodotto la riga, per
    -- verificabilità: senza di esse un valore anomalo non è diagnosticabile.
    temperature_c         DOUBLE PRECISION,
    relative_humidity_pct DOUBLE PRECISION,
    wind_speed_kmh        DOUBLE PRECISION,
    rain_24h_mm           DOUBLE PRECISION,

    computed_at TIMESTAMPTZ   NOT NULL DEFAULT now(),

    PRIMARY KEY (node_lon, node_lat, day)
);

-- L'accesso dominante è "l'ultimo stato di questo nodo prima di questo
-- giorno", cioè la lettura che ogni avanzamento fa per primo.
CREATE INDEX IF NOT EXISTS idx_fwi_state_node_day_desc
    ON fwi_state (node_lon, node_lat, day DESC);

COMMENT ON TABLE fwi_state IS
    'Catena FWI (Van Wagner 1987) per nodo meteo e giorno. Stato ricorsivo: '
    'non eliminare i giorni passati, la ricorsione li attraversa.';
