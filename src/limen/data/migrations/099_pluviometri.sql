-- Pluviometri regionali e la loro pioggia oraria, per le zone franose.
--
-- Limen non interroga la pioggia per coordinata: la chiede per una cella o un
-- comune franoso, e risponde con i pluviometri vicini e l'evento di pioggia
-- contro la soglia d'innesco (`limen.core.pioggia_frane`, MCP e API).
-- Fonti: ARPA Lombardia (CC0) e Meteotrentino (CC BY 4.0), scritte dal passo
-- notturno `pluviometri` e da `limen pluviometri-sync`.
--
-- Una riga per pluviometro e giorno UTC, non una per ora: 24 valori
-- `mm[i]` = pioggia dell'ora che finisce a giorno + i ore (i = 1..24).
-- NULL in una posizione = ora non misurata, mai zero: un pluviometro fermo
-- non è un'ora asciutta. Dal 2009 sono circa due milioni di righe invece di
-- cinquanta.

CREATE TABLE IF NOT EXISTS pluviometri (
    id            text PRIMARY KEY,
    fonte         text NOT NULL,
    codice        text NOT NULL,
    nome          text NOT NULL,
    quota_m       double precision,
    geom          geometry(Point, 4326) NOT NULL,
    dal           date,
    al            date,
    aggiornato_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (fonte, codice)
);
CREATE INDEX IF NOT EXISTS pluviometri_geog_gix ON pluviometri USING GIST ((geom::geography));

COMMENT ON TABLE pluviometri IS
    'Pluviometri delle reti regionali (id = fonte:codice). dal/al: prima e ultima misura dichiarate dalla fonte.';

CREATE TABLE IF NOT EXISTS pioggia_pluviometri (
    pluviometro_id text NOT NULL REFERENCES pluviometri(id) ON DELETE CASCADE,
    giorno         date NOT NULL,
    mm             real[] NOT NULL CHECK (array_ndims(mm) = 1 AND array_length(mm, 1) = 24),
    validata       boolean,
    PRIMARY KEY (pluviometro_id, giorno)
);

COMMENT ON COLUMN pioggia_pluviometri.mm IS
    'mm[i]: pioggia dell''ora UTC che finisce a giorno + i ore. NULL = ora non misurata, non asciutta.';
COMMENT ON COLUMN pioggia_pluviometri.validata IS
    'true: tutte le misure del giorno validate dalla fonte; false: ce ne sono di provvisorie; NULL: la fonte non lo distingue.';
