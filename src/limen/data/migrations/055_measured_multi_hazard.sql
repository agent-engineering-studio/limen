-- 055 — la vista d'insieme porta anche lei il flag (#143).
--
-- Restava fuori dalla 054 per un errore mio: il patch era scritto su
-- un'indentazione che `pg_get_viewdef` non usa, ha fallito in silenzio e la
-- migrazione e' partita senza questo pezzo. Una migrazione applicata non si
-- tocca, quindi il pezzo arriva qui.
--
-- `measured` va in coda perche' `CREATE OR REPLACE VIEW` ammette solo
-- colonne aggiunte in fondo; e dentro `ordinati` va prima, perche' li' e' la
-- finestra a decidere quale pericolo e' il peggiore e il flag deve esserle
-- disponibile.

CREATE OR REPLACE VIEW v_multi_hazard AS
WITH ordinati AS (
         SELECT m.cell_id,
            m.aoi_id,
            m.geom,
            m.centroid,
            m.hazard_type,
            m.risk_score,
            m.risk_level,
            m.computed_at,
            COALESCE(m.measured, true) AS measured,
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
    agg.hazards_at_high,
    o.measured
   FROM ordinati o
     JOIN ( SELECT mv_latest_risk.cell_id,
            count(*) FILTER (WHERE mv_latest_risk.risk_level IS NOT NULL) AS hazards_scored,
            array_agg(mv_latest_risk.hazard_type::text ORDER BY (mv_latest_risk.hazard_type::text)) FILTER (WHERE mv_latest_risk.risk_level = ANY (ARRAY['Moderate'::text, 'High'::text, 'VeryHigh'::text])) AS hazards_at_moderate,
            array_agg(mv_latest_risk.hazard_type::text ORDER BY (mv_latest_risk.hazard_type::text)) FILTER (WHERE mv_latest_risk.risk_level = ANY (ARRAY['High'::text, 'VeryHigh'::text])) AS hazards_at_high
           FROM mv_latest_risk
          GROUP BY mv_latest_risk.cell_id) agg ON agg.cell_id = o.cell_id
  WHERE o.rn = 1;;
