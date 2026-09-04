-- Pin the shadow-divergence tile layer to the default hazard (issue #82).
--
-- Migration 028 made `v_shadow_comparison` hazard-aware, which is right: it is
-- a diagnostics view and an operator wants to know which hazard a divergence
-- belongs to. But `v_shadow_divergence_tiles` is a *tile* layer that the SPA
-- loads by name (`public.v_shadow_divergence_tiles` in DivergenceMap.tsx), and
-- a tile source must yield one geometry per cell. With a second hazard enabled
-- a cell scored for both would come back twice and the layer would draw
-- overlapping polygons with different divergences on top of each other.
--
-- Same treatment as `v_risk_tiles`: pinned here, parameterised later when the
-- frontend gains a hazard selector. The hazard column stays in the output so a
-- consumer can see what it is looking at.
CREATE OR REPLACE VIEW v_shadow_divergence_tiles AS
SELECT s.cell_id, s.hazard_type, s.aoi_id, s.divergence, g.geom
FROM v_shadow_comparison s
JOIN grid_cells g ON g.id = s.cell_id
WHERE s.hazard_type = 'landslide';
