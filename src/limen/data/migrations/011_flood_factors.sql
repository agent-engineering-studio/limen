-- 011_flood_factors.sql
--
-- Activates the V1 engine's `H` (hydrology) component. The
-- deterministic engine kept `h = 0` since Phase 3; this column lets
-- it use the ISPRA hydraulic-hazard mosaic (PAI Idraulica) when the
-- per-cell value is available.
--
-- New columns on cell_static_factors:
--   * flood_hazard_class — string AA / P1 / P2 / P3 / P4 / UNKNOWN
--   * flood_hazard_norm  — numeric 0..1 mapped via the same ladder as PAI
--
-- Both are NULL by default; the engine treats NULL as `H = 0` so V1
-- baselines stay byte-identical until the operational DB is populated
-- via `limen geodata export-features` (or the static-bootstrap path).

ALTER TABLE cell_static_factors
    ADD COLUMN IF NOT EXISTS flood_hazard_class text
    CHECK (flood_hazard_class IS NULL OR flood_hazard_class IN (
        'AA', 'P1', 'P2', 'P3', 'P4', 'UNKNOWN'
    ));

ALTER TABLE cell_static_factors
    ADD COLUMN IF NOT EXISTS flood_hazard_norm double precision
    CHECK (
        flood_hazard_norm IS NULL
        OR (flood_hazard_norm >= 0.0 AND flood_hazard_norm <= 1.0)
    );

CREATE INDEX IF NOT EXISTS cell_static_factors_flood_norm_idx
    ON cell_static_factors (flood_hazard_norm)
    WHERE flood_hazard_norm IS NOT NULL;
