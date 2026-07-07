-- Slim tile view: mv_latest_risk drags the per-cell `factors` jsonb into
-- every vector tile (~3 MB per z6 tile). The map only needs identity,
-- score and class — the popup fetches the breakdown from the API.
-- pg_tileserv auto-publishes the view; tiles shrink by an order of
-- magnitude.

CREATE OR REPLACE VIEW v_risk_tiles AS
SELECT cell_id, aoi_id, risk_score, risk_level, computed_at, geom
FROM mv_latest_risk;
