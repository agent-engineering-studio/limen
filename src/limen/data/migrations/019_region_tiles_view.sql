-- Low-zoom companion of v_risk_tiles: at national zoom a 1 km cell is
-- sub-pixel, yet the cell tiles still carry every polygon (~2.5 MB per
-- z6 tile). Below the cell cutoff the map shows this 20-polygon region
-- choropleth instead; the risk_level is the level of the region's
-- worst cell (no hard-coded cutoffs — it reuses the per-cell class).

CREATE OR REPLACE VIEW v_region_tiles AS
SELECT
    a.id                                            AS aoi_id,
    a.name,
    COUNT(m.cell_id)                                AS cells,
    COUNT(*) FILTER (WHERE m.risk_level = 'Moderate')            AS moderate,
    COUNT(*) FILTER (WHERE m.risk_level IN ('High', 'VeryHigh')) AS high_or_above,
    MAX(m.risk_score)                               AS max_score,
    COALESCE(
        (array_agg(m.risk_level ORDER BY m.risk_score DESC NULLS LAST))[1],
        'None'
    )                                               AS risk_level,
    a.geom
FROM aoi a
LEFT JOIN mv_latest_risk m ON m.aoi_id = a.id AND m.risk_score IS NOT NULL
GROUP BY a.id, a.name, a.geom;
