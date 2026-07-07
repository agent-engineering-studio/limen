-- Precomputed neighbourhood exposure: landuse is static, so "is there
-- urban fabric / main infrastructure in or next to this cell" must NOT
-- be a per-request spatial query (15k cells x 2 EXISTS timed out the
-- alert list). Backfill is driven by the small sets (12.5k urban cells,
-- 2.4k infra cells) joined outward to their neighbours via the gist
-- index — seconds, once.

ALTER TABLE cell_static_factors
    ADD COLUMN IF NOT EXISTS near_urban boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS near_infra boolean NOT NULL DEFAULT false;

-- Celle adiacenti (~2 km) a tessuto urbano CORINE 11x.
UPDATE cell_static_factors f SET near_urban = TRUE
WHERE f.cell_id IN (
    SELECT DISTINCT n.id
    FROM grid_cells u
    JOIN cell_static_factors uf
      ON uf.cell_id = u.id AND uf.landuse_code LIKE '11%'
    JOIN grid_cells n ON ST_DWithin(n.geom, u.geom, 0.02)
);

-- Celle adiacenti a infrastrutture principali CORINE 12x
-- (121 industriale, 122 strade/ferrovie, 123 porti, 124 aeroporti).
UPDATE cell_static_factors f SET near_infra = TRUE
WHERE f.cell_id IN (
    SELECT DISTINCT n.id
    FROM grid_cells u
    JOIN cell_static_factors uf
      ON uf.cell_id = u.id AND uf.landuse_code LIKE '12%'
    JOIN grid_cells n ON ST_DWithin(n.geom, u.geom, 0.02)
);
