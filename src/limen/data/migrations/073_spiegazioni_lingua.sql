-- 073 — la spiegazione di una regione in più lingue.
--
-- Il sito ha una seconda lingua, l'inglese. Il racconto italiano resta quello
-- che l'AI scrive dai numeri; l'inglese ne è la traduzione, controllata sui
-- numeri prima di essere salvata. Una riga per (regione, pericolo, lingua):
-- le righe esistenti sono italiane. Il controllo di fedeltà resta
-- sull'italiano, che è il testo nato dai dati.

ALTER TABLE spiegazioni_regione ADD COLUMN IF NOT EXISTS lingua text NOT NULL DEFAULT 'it';

ALTER TABLE spiegazioni_regione DROP CONSTRAINT IF EXISTS spiegazioni_regione_pkey;
ALTER TABLE spiegazioni_regione ADD PRIMARY KEY (aoi_id, hazard_type, lingua);
