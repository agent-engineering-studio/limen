-- 085 — l'esposizione ISPRA per comune: quanta gente vive dove la mappa di
-- pericolosità dice frana o alluvione.
--
-- Gli indicatori di IdroGEO (`/api/pir/comuni/{codice}`): popolazione
-- residente (censimento ISTAT 2021) nelle aree a pericolosità frana P3+P4
-- del mosaico PAI 2020-2021 e idraulica media (P2) del mosaico 2020, più
-- edifici e imprese. Una riga per comune, riscritta dal passo notturno
-- `esposizione_ispra` quando ISPRA ripubblica (i file su disco scadono dopo
-- 30 giorni): un'allerta non deve dipendere da IdroGEO acceso durante
-- un'emergenza, e un backtest vuole un dato fermo.
--
-- Affianca il fattore OSM per cella (`core/scoring/exposure.py`), non lo
-- sostituisce, e non entra nel punteggio. `istat_code` è il PRO_COM a sei
-- cifre di `comuni`: ISPRA usa il numero, che qui si completa con gli zeri.
-- `indicatori` tiene la risposta intera (134 campi) per gli usi che verranno.
--
-- Nessuna colonna geometry, e nessun GRANT a `limen_tiles`.

CREATE TABLE IF NOT EXISTS esposizione_comuni (
    istat_code            text PRIMARY KEY,
    nome                  text NOT NULL,
    pop_residenti         integer,
    pop_frana_p3p4        integer,
    pop_frana_p3p4_pct    double precision,
    pop_idraulica_p2      integer,
    pop_idraulica_p2_pct  double precision,
    edifici               integer,
    imprese               integer,
    indicatori            jsonb NOT NULL,
    dataset_version_id    bigint REFERENCES dataset_versions (id) ON DELETE SET NULL,
    aggiornato            timestamptz NOT NULL DEFAULT now()
);
