-- 063 — le allerte ufficiali della Protezione Civile, accanto alle nostre.
--
-- Il 6 ottobre 2026 Limen dava Trieste a 0,75 «molto alto» per alluvione,
-- sulla pioggia prevista nelle 72 ore; il bollettino nazionale, per la stessa
-- zona, diceva «nessuna allerta» per oggi e domani. Chi guarda la mappa deve
-- vedere le due cose insieme, e sapere quale delle due vale.
--
-- Il Bollettino di criticità nazionale/allerta del Dipartimento della
-- Protezione Civile esce ogni giorno entro le 16:00 per le zone di allerta,
-- ed è pubblicato come GeoJSON (CC-BY 4.0): poligono, comuni, e livello per
-- rischio idrogeologico, idraulico e temporali, per oggi e per domani. È già
-- strutturato: lo si importa, non lo si interpreta.
--
-- Una riga per (giorno di validità, zona): un «Aggiornamento» o un'«errata
-- corrige» dello stesso giorno sostituisce l'emissione precedente. Livelli:
-- 0 nessuna allerta (verde), 1 gialla, 2 arancione, 3 rossa.

CREATE TABLE IF NOT EXISTS dpc_allerte (
    valido        date        NOT NULL,
    zona          text        NOT NULL,
    bollettino    text        NOT NULL,
    emesso        timestamptz NOT NULL,
    livello       smallint    NOT NULL CHECK (livello BETWEEN 0 AND 3),
    idrogeologico smallint    NOT NULL CHECK (idrogeologico BETWEEN 0 AND 3),
    idraulico     smallint    NOT NULL CHECK (idraulico BETWEEN 0 AND 3),
    temporali     smallint    NOT NULL CHECK (temporali BETWEEN 0 AND 3),
    geom          geometry(MultiPolygon, 4326) NOT NULL,
    PRIMARY KEY (valido, zona)
);

CREATE INDEX IF NOT EXISTS dpc_allerte_geom_gix ON dpc_allerte USING gist (geom);

-- Il livello di oggi sulla mappa, servito da pg_tileserv. «Oggi» è quello
-- italiano: alle 23 UTC d'estate in Italia è già domani.
CREATE OR REPLACE VIEW v_dpc_allerte_oggi AS
SELECT zona, livello, idrogeologico, idraulico, temporali, emesso, geom
FROM dpc_allerte
WHERE valido = (now() AT TIME ZONE 'Europe/Rome')::date;

COMMENT ON VIEW v_dpc_allerte_oggi IS
    'Allerte del bollettino DPC valide oggi (ora italiana), per zona: 0 verde, 1 gialla, 2 arancione, 3 rossa.';
