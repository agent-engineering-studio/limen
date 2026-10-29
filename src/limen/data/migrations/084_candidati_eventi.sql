-- 084 — i candidati della raccolta quotidiana dalla stampa (#347).
--
-- Ogni evento che l'estrattore ha trovato nei titoli, verificato o no: la
-- memoria della raccolta. Un evento rivisto il giorno dopo aggiunge le sue
-- fonti invece di duplicarsi, e un candidato con una testata sola diventa
-- verità quando arriva la seconda. Solo i `verificato` entrano in
-- `verifiche_eventi` (migrazione 074), con lo stesso slug.
--
-- Nessuna colonna geometry, e nessun GRANT a `limen_tiles`.

CREATE TABLE IF NOT EXISTS candidati_eventi (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    hazard_type   hazard_type NOT NULL,
    giorno        date NOT NULL,
    parte         text NOT NULL CHECK (parte IN ('mattina', 'pomeriggio', 'sera', 'notte', 'ignota')),
    luogo         text NOT NULL,
    regione       text,
    -- I nomi come li dà l'estrattore; i codici solo per quelli risolti in `comuni`.
    nomi_comuni   text[] NOT NULL CHECK (cardinality(nomi_comuni) > 0),
    comuni        text[] NOT NULL DEFAULT '{}',
    fonti         jsonb NOT NULL DEFAULT '[]'::jsonb,
    testate       integer NOT NULL DEFAULT 0,
    stato         text NOT NULL
        CHECK (stato IN ('verificato', 'una_testata', 'comune_ignoto')),
    slug          text,
    visto_primo   timestamptz NOT NULL DEFAULT now(),
    visto_ultimo  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS candidati_eventi_hazard_giorno_idx
    ON candidati_eventi (hazard_type, giorno);
