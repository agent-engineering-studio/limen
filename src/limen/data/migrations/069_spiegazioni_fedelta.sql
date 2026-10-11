-- 069 — quello che il modello ha letto, e se il suo racconto gli è fedele.
--
-- Una spiegazione si giudica contro i dati da cui è nata, non contro lo stato
-- di adesso: `latest_risk` cambia a ogni sweep, e un numero giusto alle 9
-- sembrerebbe inventato alle 21. `ingresso` è il messaggio esatto che il
-- modello ha ricevuto; `fedelta` il verdetto del controllo serale (il
-- controllo deterministico dei numeri e, se c'è, il giudizio del secondo
-- modello), `fedelta_at` quando è stato dato. Una spiegazione riscritta
-- azzera entrambi: il verdetto era sul testo di prima.

ALTER TABLE spiegazioni_regione ADD COLUMN IF NOT EXISTS ingresso   text;
ALTER TABLE spiegazioni_regione ADD COLUMN IF NOT EXISTS fedelta    jsonb;
ALTER TABLE spiegazioni_regione ADD COLUMN IF NOT EXISTS fedelta_at timestamptz;
