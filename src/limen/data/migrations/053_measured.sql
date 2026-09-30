-- 053 — «non misurato» non è «nessun pericolo» (#143).
--
-- IL FATTO. Un'integrazione degradata restituisce un risultato neutro, e per
-- un motore moltiplicativo il risultato neutro è **zero**. Il 29 settembre
-- 2026 il tetto giornaliero di Open-Meteo è saltato e ogni cella d'Italia si
-- è ritrovata con `flood = 0.0000` e `wildfire = 0.0000`: nella mappa, in
-- fondo alla scala YlOrRd, accanto alla scritta della classe più tranquilla.
-- Un operatore le leggeva come «qui non succede niente».
--
-- Il breakdown lo sapeva — `fire_weather: null`, `rain_mm: null` — e il
-- motore incendio lo dice per esteso nel suo commento: *«a dark cell that
-- declares why beats a plausible number nobody can source»*. La cella
-- dichiarava; nessuno la ascoltava.
--
-- Non è ricavabile dal punteggio: una cella genuinamente calma vale zero
-- anche lei. La differenza la conosce solo il breakdown, che è l'unico a
-- tenere il segnale grezzo, ed è lui a rispondere — `HazardBreakdown.
-- measured()`, la quarta proiezione accanto a `components()`,
-- `factors_payload()` e `predisposition()`. Aggiungere un pericolo non
-- tocca né questa migrazione né i suoi lettori.
--
-- NULL sullo storico significa «non lo sappiamo», e si legge come misurato:
-- retro-marcare righe scritte prima che la colonna esistesse sarebbe
-- inventare al contrario. Le righe di oggi si riscrivono al primo sweep.

ALTER TABLE risk_assessments ADD COLUMN IF NOT EXISTS measured boolean;
ALTER TABLE latest_risk      ADD COLUMN IF NOT EXISTS measured boolean;

COMMENT ON COLUMN latest_risk.measured IS
    'Falso quando il segnale dinamico che questo pericolo richiede non è '
    'arrivato: il punteggio è zero per assenza di dato, non per quiete. '
    'NULL = riga scritta prima che la colonna esistesse.';

-- `CREATE OR REPLACE` e non `DROP ... CASCADE`: aggiungere una colonna in
-- coda è permesso, e così le quattro viste che dipendono da questa restano
-- dove sono invece di essere ricreate a mano.
CREATE OR REPLACE VIEW mv_latest_risk AS
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
       r.explanation      AS explanation,
       r.measured         AS measured
FROM grid_cells g
CROSS JOIN hazards h
LEFT JOIN latest_risk r
       ON r.cell_id = g.id AND r.hazard_type = h.hazard
WHERE h.enabled;

-- Il rollup per comune è materializzato e non si può sostituire in posto.
-- CASCADE porta via `v_comune_tiles`, che infatti si ricrea qui sotto.
DROP MATERIALIZED VIEW IF EXISTS mv_comune_risk CASCADE;

CREATE MATERIALIZED VIEW mv_comune_risk AS
SELECT
    c.istat_code,
    c.name,
    c.aoi_id,
    h.hazard                                                    AS hazard_type,
    count(m.cell_id)                                            AS n_cells,
    count(*) FILTER (WHERE m.class = 'None')                    AS n_none,
    count(*) FILTER (WHERE m.class = 'Low')                     AS n_low,
    count(*) FILTER (WHERE m.class = 'Moderate')                AS n_moderate,
    count(*) FILTER (WHERE m.class = 'High')                    AS n_high,
    count(*) FILTER (WHERE m.class = 'VeryHigh')                AS n_veryhigh,
    count(*) FILTER (WHERE m.class IN ('High', 'VeryHigh'))     AS n_alert,
    max(m.score)                                                AS max_score,
    COALESCE(
        (array_agg(m.class ORDER BY m.score DESC NULLS LAST))[1],
        'None'
    )                                                           AS worst_class,
    COALESCE(
        max(m.score * (1.0 + COALESCE(f.exposure_norm, 0.0))),
        0.0
    )                                                           AS priority,
    COALESCE(max(f.exposure_norm), 0.0)                         AS exposure_rank,
    -- Basta **una** cella misurata perché il pericolo sia misurato sul
    -- comune: un buco su qualche cella è un buco, un buco su tutte è
    -- l'assenza del segnale. `COALESCE(measured, true)` perché lo storico
    -- scritto prima della colonna è ignoto, non falso; nessuna cella
    -- valutata resta `false`, che è il caso che ha aperto questa issue.
    COALESCE(bool_or(COALESCE(m.measured, true)), false)        AS measured,
    max(m.computed_at)                                          AS computed_at,
    c.geom,
    c.centroid
FROM comuni c
CROSS JOIN (SELECT hazard FROM hazards WHERE enabled) h
LEFT JOIN cell_comune cc ON cc.istat_code = c.istat_code
LEFT JOIN latest_risk m
       ON m.cell_id = cc.cell_id
      AND m.hazard_type = h.hazard
      AND m.score IS NOT NULL
LEFT JOIN cell_static_factors f ON f.cell_id = cc.cell_id
GROUP BY c.istat_code, c.name, c.aoi_id, h.hazard, c.geom, c.centroid
WITH NO DATA;

CREATE UNIQUE INDEX mv_comune_risk_pk ON mv_comune_risk (istat_code, hazard_type);
CREATE INDEX mv_comune_risk_geom_gix   ON mv_comune_risk USING gist (geom);
CREATE INDEX mv_comune_risk_aoi_idx    ON mv_comune_risk (aoi_id);
CREATE INDEX mv_comune_risk_hazard_idx ON mv_comune_risk (hazard_type, worst_class);
CREATE INDEX mv_comune_risk_prio_idx   ON mv_comune_risk (priority DESC);

REFRESH MATERIALIZED VIEW mv_comune_risk;

-- La vista della mappa, ricreata perché il DROP era CASCADE. L'attenzione
-- ora esclude i pericoli non misurati: contarli come «sotto soglia»
-- abbasserebbe il comune due volte, e la seconda è la peggiore — due
-- pericoli misurati e concomitanti perderebbero l'incremento per colpa di
-- un terzo di cui non sappiamo niente. Nessun pericolo misurato ⇒ NULL, che
-- è l'unica risposta vera e che il livello comunale disegna in grigio.
CREATE OR REPLACE VIEW v_comune_tiles AS
WITH ordinati AS (
    SELECT m.*,
           row_number() OVER (
               PARTITION BY m.istat_code
               ORDER BY CASE WHEN m.measured THEN 0 ELSE 1 END,
                        CASE m.worst_class
                            WHEN 'VeryHigh' THEN 4
                            WHEN 'High'     THEN 3
                            WHEN 'Moderate' THEN 2
                            WHEN 'Low'      THEN 1
                            ELSE 0
                        END DESC,
                        m.max_score DESC NULLS LAST,
                        m.hazard_type::text
           ) AS rn,
           max(m.priority) FILTER (WHERE m.measured)
               OVER (PARTITION BY m.istat_code) AS attention,
           bool_or(m.measured) OVER (PARTITION BY m.istat_code) AS any_measured
    FROM mv_comune_risk m
)
SELECT istat_code,
       name,
       aoi_id,
       hazard_type AS worst_hazard,
       worst_class,
       max_score,
       round(attention::numeric, 3)::double precision AS attention,
       any_measured AS measured,
       n_cells,
       n_alert,
       geom,
       centroid
FROM ordinati
WHERE rn = 1;

COMMENT ON VIEW v_comune_tiles IS
    'Una riga per comune: classe del pericolo peggiore *misurato*, quale, e '
    'il numero di attenzione (massimo delle priorità misurate). `measured` '
    'falso e `attention` NULL quando nessun pericolo ha ricevuto il suo '
    'segnale dinamico: il comune va disegnato in grigio, non in verde.';
