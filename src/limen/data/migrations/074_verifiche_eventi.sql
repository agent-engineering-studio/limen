-- 074 — il registro delle verifiche: ogni evento che ha superato il fact check.
--
-- La pagina «Verifiche» pubblica solo gli eventi previsti in anticipo, e
-- `risk_assessments` dimentica tutto dopo 14 giorni: senza questa tabella un
-- evento mancato sparisce due volte, dalla pagina per scelta e dal database
-- per retention. Ma sono proprio i mancati a dire dove il modello sbaglia
-- (Foggia, 12 ottobre 2026: 50 mm misurati sulla cella, punteggio 0,10).
--
-- Una riga per evento verificato, qualunque sia l'esito: `anticipata`,
-- `contemporanea`, `mancata`, `non_verificabile`. Gli eventi scartati al fact
-- check (una fonte sola, luogo o giorno contraddetti) non entrano: non sono
-- verità.
--
-- `misura` è l'uscita intera di anticipo.sql — corse, fattori della cella
-- peggiore, sfondo — congelata al momento della verifica, perché fra due
-- settimane le righe da cui viene non esisteranno più. Le colonne scalari ne
-- sono la proiezione per le query; la fonte è `misura`.
--
-- Non ha retention: è il truth set che cresce. Le frane verificate vanno
-- anche in `landslide_events` (source = 'stampa'), dove il backtest le legge
-- accanto a ITALICA.

CREATE TABLE IF NOT EXISTS verifiche_eventi (
    slug                  text PRIMARY KEY,
    hazard_type           hazard_type NOT NULL,
    esito                 text NOT NULL
        CHECK (esito IN ('anticipata', 'contemporanea', 'mancata', 'non_verificabile')),
    motivo                text,
    evento_at             timestamptz NOT NULL,
    -- Stessa scala di ITALICA: T1 ora, T2 mezza giornata, T3 giornata.
    precisione_ora        text NOT NULL CHECK (precisione_ora IN ('T1', 'T2', 'T3')),
    luogo                 text NOT NULL,
    regione               text,
    comuni                text[] NOT NULL CHECK (cardinality(comuni) > 0),
    geom                  geometry(Point, 4326),
    -- Stessa scala di ITALICA: P1 località entro ~1 km, P10 il comune.
    precisione_luogo      text CHECK (precisione_luogo IN ('P0', 'P1', 'P10', 'P100')),
    fonti                 jsonb NOT NULL DEFAULT '[]'::jsonb,
    anticipo_ore_moderato integer,
    anticipo_ore_alto     integer,
    classe_prevista_max   text,
    fondo_classe_max      text,
    adesso_classe_max     text,
    misura                jsonb NOT NULL,
    verificato_at         timestamptz NOT NULL DEFAULT now(),
    aggiornato_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS verifiche_eventi_hazard_time_idx
    ON verifiche_eventi (hazard_type, evento_at);

CREATE INDEX IF NOT EXISTS verifiche_eventi_geom_gix
    ON verifiche_eventi USING gist (geom);
