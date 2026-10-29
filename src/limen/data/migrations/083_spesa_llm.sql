-- 083 — quanto spende Limen chiamando Claude direttamente.
--
-- Il gateway LiteLLM ha il suo tetto (`max_budget`), ma il revisore di
-- fedeltà manda i suoi batch all'API Anthropic senza passarci (#342): senza
-- questa tabella nessuno, dentro Limen, sa quanto ha speso. Una riga per
-- chiamata, con i token come li riporta l'API e il costo calcolato con i
-- prezzi della configurazione del momento — un listino che cambia non deve
-- riscrivere la spesa di ieri.
--
-- Nessuna colonna geometry, e nessun GRANT a `limen_tiles`.

CREATE TABLE IF NOT EXISTS spesa_llm (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    registrata_at  timestamptz NOT NULL DEFAULT now(),
    origine        text NOT NULL,
    riferimento    text,
    modello        text NOT NULL,
    input_tokens   integer NOT NULL CHECK (input_tokens >= 0),
    output_tokens  integer NOT NULL CHECK (output_tokens >= 0),
    costo_usd      numeric(12, 6) NOT NULL CHECK (costo_usd >= 0)
);
CREATE INDEX IF NOT EXISTS spesa_llm_registrata_idx ON spesa_llm (registrata_at);
