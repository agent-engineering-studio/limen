-- 052 — l'esposizione entra nel rollup, e ne esce un numero per comune.
--
-- IL FATTO. Il rollup per comune calcolava `exposure_rank` leggendo
-- `factors->>'e'`, una chiave che **solo il breakdown delle frane** ha:
-- per incendio e alluvione valeva zero. Ma «quante persone e quante strade
-- ci sono intorno» è una proprietà del posto, non del pericolo, ed è
-- esattamente ciò che serve per portare un comune all'attenzione.
--
-- Ora l'esposizione è materializzata per cella in
-- `cell_static_factors.exposure_norm`, calcolata da `limen calibrate` con la
-- stessa funzione pura che il dispacciatore degli alert usa da sempre. In
-- SQL non si poteva chiamare, e riscriverla qui avrebbe voluto dire due
-- copie delle stesse soglie, libere di divergere.
--
-- Da lì il rollup ricava per (comune, pericolo) la **priorità**:
--
--     priorità = punteggio della cella peggiore per uno più la sua esposizione
--
-- che è la formula degli alert, non una nuova. Il numero unico del comune —
-- il massimo fra i pericoli, con l'incremento quando sono più di uno — lo
-- compone `limen.core.cascades.attention`, perché quella parte ha una soglia
-- di classe e le soglie stanno nella configurazione, non in SQL.

ALTER TABLE cell_static_factors
    ADD COLUMN IF NOT EXISTS exposure_norm double precision;

COMMENT ON COLUMN cell_static_factors.exposure_norm IS
    'Esposizione della cella in [0, cap]: tessuto urbano, distanza da strade '
    'e ferrovie. Indipendente dal pericolo (il termine WUI è escluso di '
    'proposito). La scrive `limen calibrate`.';

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
    -- La priorità: la stessa formula degli alert, applicata cella per cella
    -- e poi presa al massimo. Prenderla sul solo massimo del punteggio
    -- sarebbe diverso e sbagliato: la cella più pericolosa e quella più
    -- esposta non sono sempre la stessa, e ciò che conta è la peggiore
    -- combinazione delle due.
    COALESCE(
        max(m.score * (1.0 + COALESCE(f.exposure_norm, 0.0))),
        0.0
    )                                                           AS priority,
    -- Quanto è esposto il comune, per poterlo dire a parole accanto al
    -- numero: è il massimo sulle sue celle, non una media, perché una sola
    -- cella sopra un paese basta a rendere il comune un posto da guardare.
    COALESCE(max(f.exposure_norm), 0.0)                         AS exposure_rank,
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

-- La vista della mappa, ricreata perché il DROP era CASCADE. Ordina sul
-- peggiore come prima, e porta anche la priorità: il livello comunale può
-- così colorare per classe e ordinare l'etichetta per attenzione.
CREATE OR REPLACE VIEW v_comune_tiles AS
WITH ordinati AS (
    SELECT m.*,
           row_number() OVER (
               PARTITION BY m.istat_code
               ORDER BY CASE m.worst_class
                            WHEN 'VeryHigh' THEN 4
                            WHEN 'High'     THEN 3
                            WHEN 'Moderate' THEN 2
                            WHEN 'Low'      THEN 1
                            ELSE 0
                        END DESC,
                        m.max_score DESC NULLS LAST,
                        m.hazard_type::text
           ) AS rn,
           max(m.priority) OVER (PARTITION BY m.istat_code) AS attention
    FROM mv_comune_risk m
)
SELECT istat_code,
       name,
       aoi_id,
       hazard_type AS worst_hazard,
       worst_class,
       max_score,
       round(attention::numeric, 3)::double precision AS attention,
       n_cells,
       n_alert,
       geom,
       centroid
FROM ordinati
WHERE rn = 1;

COMMENT ON VIEW v_comune_tiles IS
    'Una riga per comune: classe del pericolo peggiore, quale, e il numero '
    'di attenzione (massimo delle priorità). Sorgente del livello comunale '
    'della mappa, che con il rollup per pericolo disegnerebbe altrimenti tre '
    'poligoni sovrapposti.';
