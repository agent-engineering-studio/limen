-- 048 — la mappa smette di rigenerarsi intera a ogni sweep (#125).
--
-- IL FATTO. `mv_latest_risk` ricavava "l'ultimo punteggio per cella"
-- applicando ROW_NUMBER() a **tutta** `risk_assessments`. Lo sweep orario
-- scrive una riga per cella e per pericolo: 312.000 celle × 3 pericoli × 24
-- ore fanno ~19 milioni di righe al giorno (misurato: 18.898.377 nella sola
-- partizione del 2026-09-20). Ordinarle tutte per produrne 937.000 costava
-- oltre venti minuti, contro un debounce di cinque: il refresh non finiva
-- prima che il successivo fosse già dovuto, e la mappa restava indietro.
--
-- COSA HO PROVATO PRIMA. Riscrivere la vista con un LEFT JOIN LATERAL che
-- usa l'indice (cell_id, hazard_type, computed_at DESC) e prende una riga
-- per cella: **oltre 30 minuti senza finire**, quindi non è la forma della
-- query. Il costo è nel volume, e nessuna query che lo attraversa può
-- essere veloce.
--
-- LA CORREZIONE. Chi scrive sa già qual è l'ultimo punteggio: è quello che
-- sta scrivendo. `latest_risk` tiene una riga per (cella, pericolo),
-- aggiornata in upsert dallo stesso passo che persiste lo sweep — un
-- INSERT ... ON CONFLICT insiemistico sulle righe appena scritte, non una
-- scansione dello storico. `mv_latest_risk` diventa una **vista normale**:
-- niente più refresh, niente più debounce, e la mappa mostra il punteggio
-- nell'istante in cui viene persistito.
--
-- Perché una vista e non una materializzata piccola: una materializzata
-- avrebbe comunque un refresh da schedulare e una finestra in cui mostra il
-- passato. La vista unisce `grid_cells` (GIST sulla geometria) a
-- `latest_risk` per chiave primaria; una tile chiede un bbox, quindi legge
-- poche migliaia di celle e altrettante letture per chiave.
--
-- `refresh_mv_latest_risk()` resta, con lo stesso nome e gli stessi codici
-- di ritorno, perché è l'invariante che il resto del codice conosce: ora
-- aggiorna solo il rollup per comune, che è un aggregato e una vista
-- materializzata deve restare.

-- ---------------------------------------------------------------------------
-- 1. Lo stato corrente, scritto una volta e poi mantenuto in upsert
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS latest_risk (
    cell_id          text        NOT NULL,
    hazard_type      hazard_type NOT NULL,
    score            double precision,
    class            text,
    horizon          text,
    pipeline_version text,
    computed_at      timestamptz NOT NULL,
    factors          jsonb,
    explanation      jsonb,
    PRIMARY KEY (cell_id, hazard_type)
);

-- La vista filtrava per classe e per pericolo con i suoi indici; ora quei
-- filtri arrivano qui.
CREATE INDEX IF NOT EXISTS latest_risk_hazard_class_idx ON latest_risk (hazard_type, class);
CREATE INDEX IF NOT EXISTS latest_risk_computed_idx     ON latest_risk (computed_at DESC);

-- Popolamento iniziale dalla materializzata che sta per sparire: è già
-- materializzata, quindi è una lettura di 937.000 righe e non il calcolo da
-- venti minuti. Su un database nuovo non c'è niente da copiare.
INSERT INTO latest_risk (
    cell_id, hazard_type, score, class, horizon, pipeline_version,
    computed_at, factors, explanation
)
SELECT cell_id, hazard_type, risk_score, risk_level, horizon, pipeline_version,
       computed_at, factors, explanation
FROM mv_latest_risk
WHERE computed_at IS NOT NULL
ON CONFLICT (cell_id, hazard_type) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 2. La vista prende il posto della materializzata
-- ---------------------------------------------------------------------------
-- CASCADE: le quattro viste dipendenti vengono ricreate qui sotto, identiche.
-- Senza CASCADE il DROP fallirebbe; con CASCADE e senza le ricreazioni la
-- mappa resterebbe senza tile, quindi le due cose stanno nella stessa
-- migrazione e nella stessa transazione.
DROP MATERIALIZED VIEW IF EXISTS mv_latest_risk CASCADE;

-- Il CROSS JOIN resta per la stessa ragione di prima: una riga per cella e
-- per pericolo abilitato, anche quando quel pericolo non è ancora stato
-- valutato su quella cella.
CREATE VIEW mv_latest_risk AS
SELECT g.id               AS cell_id,
       h.hazard           AS hazard_type,
       g.aoi_id           AS aoi_id,
       g.geom             AS geom,
       g.centroid         AS centroid,
       g.area_km2         AS area_km2,
       r.score            AS risk_score,
       r.class            AS risk_level,
       r.horizon          AS horizon,
       r.pipeline_version AS pipeline_version,
       r.computed_at      AS computed_at,
       r.factors          AS factors,
       r.explanation      AS explanation
FROM grid_cells g
CROSS JOIN hazards h
LEFT JOIN latest_risk r
       ON r.cell_id = g.id AND r.hazard_type = h.hazard
WHERE h.enabled;

-- ---------------------------------------------------------------------------
-- 3. Le dipendenti, ricreate come erano
-- ---------------------------------------------------------------------------
CREATE MATERIALIZED VIEW mv_comune_risk AS
 SELECT c.istat_code,
    c.name,
    c.aoi_id,
    count(m.cell_id) AS n_cells,
    count(*) FILTER (WHERE m.risk_level = 'None'::text) AS n_none,
    count(*) FILTER (WHERE m.risk_level = 'Low'::text) AS n_low,
    count(*) FILTER (WHERE m.risk_level = 'Moderate'::text) AS n_moderate,
    count(*) FILTER (WHERE m.risk_level = 'High'::text) AS n_high,
    count(*) FILTER (WHERE m.risk_level = 'VeryHigh'::text) AS n_veryhigh,
    count(*) FILTER (WHERE m.risk_level = ANY (ARRAY['High'::text, 'VeryHigh'::text])) AS n_alert,
    max(m.risk_score) AS max_score,
    COALESCE((array_agg(m.risk_level ORDER BY m.risk_score DESC NULLS LAST))[1], 'None'::text) AS worst_class,
    COALESCE(sum((m.factors ->> 'e'::text)::double precision) FILTER (WHERE m.risk_level = ANY (ARRAY['High'::text, 'VeryHigh'::text])), 0::double precision) AS exposure_rank,
    c.geom,
    c.centroid
   FROM comuni c
     LEFT JOIN cell_comune cc ON cc.istat_code = c.istat_code
     LEFT JOIN mv_latest_risk m ON m.cell_id = cc.cell_id AND m.hazard_type = 'landslide'::hazard_type AND m.risk_score IS NOT NULL
  GROUP BY c.istat_code, c.name, c.aoi_id, c.geom, c.centroid
WITH NO DATA;
CREATE VIEW v_risk_tiles AS
 SELECT cell_id,
    aoi_id,
    risk_score,
    risk_level,
    computed_at,
    geom
   FROM mv_latest_risk
  WHERE hazard_type = 'landslide'::hazard_type;
CREATE VIEW v_region_tiles AS
 SELECT a.id AS aoi_id,
    a.name,
    count(m.cell_id) AS cells,
    count(*) FILTER (WHERE m.risk_level = 'Moderate'::text) AS moderate,
    count(*) FILTER (WHERE m.risk_level = ANY (ARRAY['High'::text, 'VeryHigh'::text])) AS high_or_above,
    max(m.risk_score) AS max_score,
    COALESCE((array_agg(m.risk_level ORDER BY m.risk_score DESC NULLS LAST))[1], 'None'::text) AS risk_level,
    a.geom
   FROM aoi a
     LEFT JOIN mv_latest_risk m ON m.aoi_id = a.id AND m.hazard_type = 'landslide'::hazard_type AND m.risk_score IS NOT NULL
  GROUP BY a.id, a.name, a.geom;
CREATE VIEW v_multi_hazard AS
 WITH ordinati AS (
         SELECT m.cell_id,
            m.aoi_id,
            m.geom,
            m.centroid,
            m.hazard_type,
            m.risk_score,
            m.risk_level,
            m.computed_at,
                CASE m.risk_level
                    WHEN 'VeryHigh'::text THEN 4
                    WHEN 'High'::text THEN 3
                    WHEN 'Moderate'::text THEN 2
                    WHEN 'Low'::text THEN 1
                    ELSE 0
                END AS rango,
            row_number() OVER (PARTITION BY m.cell_id ORDER BY (
                CASE m.risk_level
                    WHEN 'VeryHigh'::text THEN 4
                    WHEN 'High'::text THEN 3
                    WHEN 'Moderate'::text THEN 2
                    WHEN 'Low'::text THEN 1
                    ELSE 0
                END) DESC, m.risk_score DESC NULLS LAST, (m.hazard_type::text)) AS rn
           FROM mv_latest_risk m
        )
 SELECT o.cell_id,
    o.aoi_id,
    o.geom,
    o.centroid,
    o.hazard_type AS worst_hazard,
    o.risk_level AS worst_level,
    o.risk_score AS worst_score,
    o.computed_at AS worst_computed_at,
    agg.hazards_scored,
    agg.hazards_at_moderate,
    agg.hazards_at_high
   FROM ordinati o
     JOIN ( SELECT mv_latest_risk.cell_id,
            count(*) FILTER (WHERE mv_latest_risk.risk_level IS NOT NULL) AS hazards_scored,
            array_agg(mv_latest_risk.hazard_type::text ORDER BY (mv_latest_risk.hazard_type::text)) FILTER (WHERE mv_latest_risk.risk_level = ANY (ARRAY['Moderate'::text, 'High'::text, 'VeryHigh'::text])) AS hazards_at_moderate,
            array_agg(mv_latest_risk.hazard_type::text ORDER BY (mv_latest_risk.hazard_type::text)) FILTER (WHERE mv_latest_risk.risk_level = ANY (ARRAY['High'::text, 'VeryHigh'::text])) AS hazards_at_high
           FROM mv_latest_risk
          GROUP BY mv_latest_risk.cell_id) agg ON agg.cell_id = o.cell_id
  WHERE o.rn = 1;

CREATE UNIQUE INDEX IF NOT EXISTS mv_comune_risk_pk       ON mv_comune_risk (istat_code);
CREATE INDEX IF NOT EXISTS mv_comune_risk_geom_gix        ON mv_comune_risk USING gist (geom);
CREATE INDEX IF NOT EXISTS mv_comune_risk_aoi_idx         ON mv_comune_risk (aoi_id);
REFRESH MATERIALIZED VIEW mv_comune_risk;

-- ---------------------------------------------------------------------------
-- 4. La ricostruzione dallo storico, esplicita e fuori dal percorso caldo
-- ---------------------------------------------------------------------------
-- La scansione costosa non sparisce: cambia chi la chiede e quando. Serve
-- dopo un ripristino, dopo un'ingestione che ha scritto in `risk_assessments`
-- per altre vie, e ai test che seminano righe a mano. Non la chiama nessun
-- job: se tornasse nel percorso orario, tornerebbe il problema della #125.
--
-- `horizon NOT LIKE '+%'` esclude le righe previsionali: le scrive
-- `forecast_history` per il grafico dell'andamento, e sotto la vecchia vista
-- diventavano «l'ultimo punteggio» della cella perché erano le più recenti.
-- La mappa mostrava una previsione come se fosse lo stato corrente.
CREATE OR REPLACE FUNCTION rebuild_latest_risk() RETURNS bigint
LANGUAGE plpgsql
AS $$
DECLARE
    n bigint;
BEGIN
    INSERT INTO latest_risk (
        cell_id, hazard_type, score, class, horizon, pipeline_version,
        computed_at, factors, explanation
    )
    SELECT DISTINCT ON (cell_id, hazard_type)
           cell_id, hazard_type, score, class, horizon, pipeline_version,
           computed_at, factors, explanation
    FROM risk_assessments
    WHERE horizon NOT LIKE '+%'
    ORDER BY cell_id, hazard_type, computed_at DESC
    ON CONFLICT (cell_id, hazard_type) DO UPDATE
    SET score            = EXCLUDED.score,
        class            = EXCLUDED.class,
        horizon          = EXCLUDED.horizon,
        pipeline_version = EXCLUDED.pipeline_version,
        computed_at      = EXCLUDED.computed_at,
        factors          = EXCLUDED.factors,
        explanation      = EXCLUDED.explanation
    WHERE latest_risk.computed_at <= EXCLUDED.computed_at;
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END $$;

-- ---------------------------------------------------------------------------
-- 5. Il refresh non ha più una materializzata da rigenerare
-- ---------------------------------------------------------------------------
-- Stessa firma e stessi codici di ritorno (1 = fatto, 0 = saltato per
-- debounce, -1 = fallito): i chiamanti non cambiano. Il debounce resta
-- perché il rollup per comune è un aggregato su 937.000 righe e non ha senso
-- rifarlo per ogni AOI di uno sweep nazionale.
CREATE OR REPLACE FUNCTION refresh_mv_latest_risk() RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    last_refresh timestamptz;
BEGIN
    SELECT refreshed_at INTO last_refresh
    FROM mv_refresh_state WHERE view_name = 'mv_latest_risk'
    FOR UPDATE;

    IF last_refresh > now() - interval '5 minutes' THEN
        RETURN 0;
    END IF;

    UPDATE mv_refresh_state SET refreshed_at = now()
    WHERE view_name = 'mv_latest_risk';

    BEGIN
        PERFORM refresh_mv_comune_risk();
    EXCEPTION
        WHEN OTHERS THEN
            UPDATE mv_refresh_state SET refreshed_at = last_refresh
            WHERE view_name = 'mv_latest_risk';
            RAISE NOTICE 'refresh_mv_latest_risk failed: %', SQLERRM;
            RETURN -1;
    END;
    RETURN 1;
END $$;
