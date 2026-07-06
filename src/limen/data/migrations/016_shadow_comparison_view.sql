-- Analyst view for the shadow-observation period: latest champion score
-- vs latest challenger probability per cell, with the divergence that
-- the promotion decision will be judged on. Read-only, not in any hot
-- path (DISTINCT ON over the (cell_id, computed_at DESC) indexes).

CREATE OR REPLACE VIEW v_shadow_comparison AS
WITH champion AS (
    SELECT DISTINCT ON (cell_id)
           cell_id, score, class, computed_at
    FROM risk_assessments
    ORDER BY cell_id, computed_at DESC
),
challenger AS (
    SELECT DISTINCT ON (cell_id)
           cell_id, probability, risk_class, model_version, computed_at
    FROM model_runs
    WHERE role = 'challenger'
    ORDER BY cell_id, computed_at DESC
)
SELECT
    ch.cell_id,
    g.aoi_id,
    ch.score                    AS champion_score,
    ch.class                    AS champion_class,
    ml.probability              AS ml_probability,
    ml.risk_class               AS ml_class,
    ml.probability - ch.score   AS divergence,
    ml.model_version,
    ch.computed_at              AS champion_at,
    ml.computed_at              AS challenger_at
FROM champion ch
JOIN challenger ml USING (cell_id)
JOIN grid_cells g ON g.id = ch.cell_id;
