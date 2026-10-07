-- 067 — i comuni che non contengono il centro di nessuna cella (#152).
--
-- `cell_comune` assegna ogni cella da 1 km² al comune che ne contiene il
-- centro: una cella, un comune. Cinque comuni d'Italia sono più piccoli di
-- una cella, o stretti fra i centri di quelle vicine, e non ne ricevevano
-- nessuna — niente punteggio, niente previsione, nessuna riga nella lista.
-- Fra questi Atrani, il comune più piccolo d'Italia, travolto dal Dragone il
-- 9 settembre 2010: proprio un posto che il sistema deve vedere.
--
-- Il ripiego sta in una tabella sua e non in `cell_comune`: lì `cell_id` è
-- chiave, e una cella contata in due comuni cambierebbe i conteggi dei
-- vicini. Qui stanno soltanto le celle che **intersecano** un comune senza
-- celle proprie (almeno 1.000 m² di sovrapposizione: un bordo che sfiora
-- non conta), e `cell_comune_tutte` le unisce alle assegnazioni ordinarie.
-- Gli altri 7.896 comuni non cambiano di una cella.
--
-- Il ripiego si ricalcola con `refresh_cell_comune_extra()`, che `limen
-- seed-comuni` chiama dopo aver assegnato i centri.

CREATE TABLE IF NOT EXISTS cell_comune_extra (
    istat_code text NOT NULL,
    cell_id    text NOT NULL,
    PRIMARY KEY (istat_code, cell_id)
);

CREATE OR REPLACE FUNCTION refresh_cell_comune_extra() RETURNS integer
LANGUAGE plpgsql AS $$
DECLARE
    n integer;
BEGIN
    DELETE FROM cell_comune_extra;
    INSERT INTO cell_comune_extra (istat_code, cell_id)
    SELECT c.istat_code, g.id
    FROM comuni c
    JOIN grid_cells g ON ST_Intersects(g.geom, c.geom)
    WHERE NOT EXISTS (SELECT 1 FROM cell_comune cc WHERE cc.istat_code = c.istat_code)
      AND ST_Area(ST_Intersection(g.geom, c.geom)::geography) >= 1000;
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END;
$$;

SELECT refresh_cell_comune_extra();

CREATE OR REPLACE VIEW cell_comune_tutte AS
SELECT cell_id, istat_code FROM cell_comune
UNION ALL
SELECT cell_id, istat_code FROM cell_comune_extra;

-- Il rollup per comune legge la vista. È materializzato e non si sostituisce
-- in posto: CASCADE porta via `v_comune_tiles`, ricreata identica qui sotto.
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
LEFT JOIN cell_comune_tutte cc ON cc.istat_code = c.istat_code
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
