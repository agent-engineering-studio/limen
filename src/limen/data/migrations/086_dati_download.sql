-- 086 — lo stato dei download dei dati statici (#402, epic #409).
--
-- Una riga per voce del catalogo (`src/limen/config/dati.yaml`): chi chiede un
-- download la mette `in_coda` e manda un NOTIFY sul canale `dati_download`, il
-- worker la prende, la porta `in_corso`, ne scrive l'avanzamento e la chiude
-- `fatto` o `errore`. La pagina di installazione (#404) legge da qui.
--
-- Una riga sola per voce, non uno storico: la domanda è «a che punto è», e il
-- dettaglio di come è andata sta nei log del worker.
--
-- `byte_totali` è la stima del catalogo (`peso_gb`), non il Content-Length:
-- molte voci sono decine di file, e alcune (EFFIS) non sono file.
--
-- Nessuna colonna geometry, e nessun GRANT a `limen_tiles`.

CREATE TABLE IF NOT EXISTS dati_download (
    voce          text PRIMARY KEY,
    stato         text NOT NULL
        CHECK (stato IN ('in_coda', 'in_corso', 'fatto', 'errore')),
    byte_fatti    bigint NOT NULL DEFAULT 0 CHECK (byte_fatti >= 0),
    byte_totali   bigint CHECK (byte_totali >= 0),
    richiesto_il  timestamptz NOT NULL DEFAULT now(),
    avviato_il    timestamptz,
    aggiornato_il timestamptz NOT NULL DEFAULT now(),
    finito_il     timestamptz,
    -- Quante volte il worker l'ha presa. Un download che uccide il processo
    -- (OOM, segfault di GDAL) verrebbe ripreso a ogni riavvio, all'infinito:
    -- oltre un tetto la voce si chiude in errore invece di tornare in coda.
    tentativi     integer NOT NULL DEFAULT 0 CHECK (tentativi >= 0),
    -- In italiano, per chi installa: il traceback resta nei log.
    errore        text
);

-- Il worker prende la richiesta più vecchia fra quelle in coda.
CREATE INDEX IF NOT EXISTS dati_download_coda_idx
    ON dati_download (richiesto_il)
    WHERE stato = 'in_coda';
