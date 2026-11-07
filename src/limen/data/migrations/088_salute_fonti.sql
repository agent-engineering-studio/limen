-- 088 — come stanno le fonti esterne (#408, epic #409).
--
-- Una riga per fonte (`limen.integrations.salute.FONTI`): l'ultima chiamata
-- riuscita e l'ultimo errore, con il messaggio in italiano. La scrive il
-- battito del worker riversando il registro del processo; la legge la pagina
-- «Salute». Come `dati_download`, una riga sola e non uno storico: la domanda
-- è «adesso va?», e il dettaglio sta nei log del worker.
--
-- Nessuna colonna geometry, e nessun GRANT a `limen_tiles`.

CREATE TABLE IF NOT EXISTS salute_fonti (
    fonte          text PRIMARY KEY,
    ultimo_ok      timestamptz,
    ultimo_errore  timestamptz,
    errore         text,
    aggiornato_il  timestamptz NOT NULL DEFAULT now()
);
