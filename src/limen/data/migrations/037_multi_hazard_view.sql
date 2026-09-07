-- Vista "quadro unico": la classe peggiore fra i pericoli, per cella (#58).
--
-- `mv_latest_risk` ha una riga per (cella, pericolo). Una sorgente di tile
-- deve dare **una** geometria per cella, ed è il motivo per cui le viste a
-- valle sono fissate sul pericolo di default dalla migrazione 028.
--
-- Questa vista risolve la cosa nel modo opposto: invece di scegliere un
-- pericolo, aggrega. Una riga per cella, con la classe peggiore, il pericolo
-- che l'ha determinata, e l'elenco di quelli che superano la soglia — così un
-- operatore che guarda la mappa unica sa subito *quale* pericolo sta guardando
-- in quella cella, che è l'informazione che una semplice classe massima
-- perderebbe.
--
-- Non materializzata: legge `mv_latest_risk`, che è già materializzata e
-- rinfrescata da `refresh_mv_latest_risk()`. Una seconda matview andrebbe
-- rinfrescata in cascata e potrebbe restare indietro rispetto alla prima,
-- mostrando un quadro unico più vecchio dei singoli pericoli.

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
           -- L'ordine delle classi non è alfabetico: va dichiarato, o
           -- 'VeryHigh' finirebbe dopo 'None'.
           CASE m.risk_level
               WHEN 'VeryHigh' THEN 4
               WHEN 'High'     THEN 3
               WHEN 'Moderate' THEN 2
               WHEN 'Low'      THEN 1
               ELSE 0
           END AS rango,
           ROW_NUMBER() OVER (
               PARTITION BY m.cell_id
               ORDER BY CASE m.risk_level
                            WHEN 'VeryHigh' THEN 4
                            WHEN 'High'     THEN 3
                            WHEN 'Moderate' THEN 2
                            WHEN 'Low'      THEN 1
                            ELSE 0
                        END DESC,
                        m.risk_score DESC NULLS LAST,
                        -- Spareggio sul nome del pericolo: senza, due
                        -- pericoli a pari classe e pari punteggio si
                        -- alternerebbero fra un refresh e l'altro e la mappa
                        -- sembrerebbe cambiare senza motivo.
                        m.hazard_type::text
           ) AS rn
    FROM mv_latest_risk m
)
SELECT o.cell_id,
       o.aoi_id,
       o.geom,
       o.centroid,
       -- Il pericolo peggiore e la sua classe: è ciò che colora la cella.
       o.hazard_type      AS worst_hazard,
       o.risk_level       AS worst_level,
       o.risk_score       AS worst_score,
       o.computed_at      AS worst_computed_at,
       -- Quanti pericoli sono valutati su questa cella, e quali arrivano
       -- almeno a Moderate. L'elenco è ciò che distingue "una cella a rischio
       -- alto" da "una cella a rischio alto per tre motivi insieme".
       agg.hazards_scored,
       agg.hazards_at_moderate,
       agg.hazards_at_high
FROM ordinati o
JOIN (
    SELECT cell_id,
           count(*) FILTER (WHERE risk_level IS NOT NULL) AS hazards_scored,
           array_agg(hazard_type::text ORDER BY hazard_type::text)
             FILTER (WHERE risk_level IN ('Moderate', 'High', 'VeryHigh'))
             AS hazards_at_moderate,
           array_agg(hazard_type::text ORDER BY hazard_type::text)
             FILTER (WHERE risk_level IN ('High', 'VeryHigh'))
             AS hazards_at_high
    FROM mv_latest_risk
    GROUP BY cell_id
) agg ON agg.cell_id = o.cell_id
WHERE o.rn = 1;

COMMENT ON VIEW v_multi_hazard IS
    'Quadro unico per cella (#58): classe peggiore fra i pericoli abilitati, '
    'pericolo che la determina, ed elenco di quelli oltre soglia. Una riga per '
    'cella, adatta a una sorgente di tile.';

-- ---------------------------------------------------------------------------
-- Sorgente di tile del quadro unico
-- ---------------------------------------------------------------------------
-- Stessa forma di `risk_at`: una funzione, perché pg_tileserv pubblica le
-- funzioni con i parametri in query string e qui non ce ne sono da passare —
-- ma la funzione tiene l'ordine dei feature deterministico, che una vista non
-- garantisce (migrazione 029).
CREATE OR REPLACE FUNCTION public.multi_hazard_at(
    z integer, x integer, y integer
) RETURNS bytea AS $$
WITH bounds AS (
    SELECT ST_TileEnvelope(z, x, y) AS b
),
mvt AS (
    SELECT ST_AsMVTGeom(ST_Transform(v.geom, 3857), bounds.b) AS geom,
           v.cell_id,
           v.worst_hazard::text AS worst_hazard,
           v.worst_level,
           v.worst_score,
           v.hazards_scored,
           array_to_string(v.hazards_at_high, ',') AS hazards_at_high
    FROM v_multi_hazard v, bounds
    WHERE v.worst_level IS NOT NULL
      AND ST_Intersects(ST_Transform(v.geom, 3857), bounds.b)
)
SELECT ST_AsMVT(mvt.*, 'public.v_multi_hazard', 4096, 'geom' ORDER BY mvt.cell_id)
FROM mvt;
$$ LANGUAGE sql STABLE PARALLEL SAFE;

COMMENT ON FUNCTION public.multi_hazard_at IS
    'Tile del quadro unico (#58). Il layer MVT si chiama public.v_multi_hazard: '
    'il nome dentro il tile non è il path da cui si scarica.';
