-- Tile view for the ML-diagnostics divergence map (issue #26). pg_tileserv
-- auto-publishes it as public.v_shadow_divergence_tiles. Per cell: the
-- divergence (ml_probability - champion_score) of the latest run of each
-- engine, plus the cell geometry. Read-only, not in any hot path; the
-- operational risk map never uses it.

CREATE OR REPLACE VIEW v_shadow_divergence_tiles AS
SELECT s.cell_id, s.aoi_id, s.divergence, g.geom
FROM v_shadow_comparison s
JOIN grid_cells g ON g.id = s.cell_id;
