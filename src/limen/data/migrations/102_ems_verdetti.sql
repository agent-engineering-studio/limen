-- 102_ems_verdetti.sql
--
-- Il vaglio radar delle mappe Copernicus EMS (#713), letto dai rapporti che la
-- libreria `copernicus-ems` scrive accanto a ogni coppia Sentinel-1:
-- `<stem>_quality.json` (verdetto) e `<stem>_agreement.json` + `.geojson`
-- (dove mappa e radar concordano). Limen li legge come formato di file, non
-- importa i moduli della libreria.
--
-- Il verdetto è uno **screening, non un giudizio**: «to check» vuol dire che
-- qualcuno dovrebbe riguardare la mappa, mai che la mappa è sbagliata. Il
-- backtest lo usa per riportare i punteggi due volte (tutte le mappe, e senza
-- quelle «to check»), mai per togliere una mappa in silenzio.
--
-- Una riga per prodotto EMS. `mask_id` è l'id di `flood_observation_masks` e il
-- prefisso degli id di `flood_events` (`EMSR664-aoi01-GRA0`): è la chiave con
-- cui il backtest toglie insieme i poligoni allagati e la maschera di un
-- prodotto. Non è una chiave esterna: un rapporto può arrivare prima
-- dell'ingest, e il comando lo segnala invece di scartarlo.

CREATE TABLE IF NOT EXISTS ems_verdetti (
    activation_code   text NOT NULL,
    product           text NOT NULL,
    aoi_label         text NOT NULL,
    mask_id           text NOT NULL,
    pair_stem         text NOT NULL,
    -- NULL quando c'è solo il rapporto di accordo e non dice il verdetto.
    verdict           text CHECK (verdict IN ('coherent', 'to check', 'not assessable')),
    reason            text,
    flags             jsonb NOT NULL DEFAULT '[]'::jsonb,
    measurements      jsonb NOT NULL DEFAULT '{}'::jsonb,
    thresholds        jsonb,
    gap_hours         double precision,
    resolution_m      double precision,
    -- Accordo radar. `independent = false`: mappa tracciata sullo stesso
    -- Sentinel-1, quindi `km2.confirmed` e `scores` non provano niente.
    agreement_computed boolean,
    agreement_reason  text,
    independent       boolean,
    km2               jsonb,
    scores            jsonb,
    quality_file      text,
    agreement_file    text,
    agreement_geojson text,
    updated_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (activation_code, product)
);

-- Acqua che il radar vede **fuori** dalla mappa, in chiazze di almeno 1 km²
-- (classe `candidate`). Può essere acqua non mappata come terreno arato e
-- bagnato: **mai verità, mai un allarme mancato**. Sta qui perché qualcuno la
-- riguardi, non per il backtest, che non legge questa tabella.
CREATE TABLE IF NOT EXISTS ems_acqua_possibile (
    activation_code text NOT NULL,
    product         text NOT NULL,
    mask_id         text NOT NULL,
    area_km2        double precision,
    geom            geometry(MultiPolygon, 4326) NOT NULL,
    PRIMARY KEY (activation_code, product)
);

CREATE INDEX IF NOT EXISTS ems_acqua_possibile_geom_gix
    ON ems_acqua_possibile USING gist (geom);

-- Acqua mappata **e** vista dal radar (classe `confirmed`): la verità più
-- solida. Vale solo con `independent = true`; le righe di mappe tracciate su
-- Sentinel-1 restano per trasparenza e chi legge filtra. Le tre tabelle si
-- scrivono nella stessa transazione, così `independent` non diverge da
-- quello di `ems_verdetti`.
CREATE TABLE IF NOT EXISTS ems_acqua_confermata (
    activation_code text NOT NULL,
    product         text NOT NULL,
    mask_id         text NOT NULL,
    independent     boolean NOT NULL,
    area_km2        double precision,
    geom            geometry(MultiPolygon, 4326) NOT NULL,
    PRIMARY KEY (activation_code, product)
);

CREATE INDEX IF NOT EXISTS ems_acqua_confermata_geom_gix
    ON ems_acqua_confermata USING gist (geom);
