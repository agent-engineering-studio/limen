-- 051 — il rollup per comune smette di parlare di un pericolo solo.
--
-- IL FATTO. `mv_comune_risk` era fissata sulle frane in SQL (migrazione 028),
-- e la dashboard lo dichiarava con un badge. Conseguenza: scegliendo
-- «Alluvione» o «Incendio» metà colonna continuava a parlare d'altro, e la
-- domanda che un tecnico comunale fa davvero — «il mio comune, per tutti i
-- pericoli» — non aveva una superficie che la rispondesse.
--
-- Ora la riga è per **(comune, pericolo)**: 7.901 comuni × 3 pericoli
-- abilitati fanno 23.703 righe, che è niente, e la colonna può mostrare i
-- tre indicatori affiancati senza una query per pericolo.
--
-- La classe del comune resta quella della **cella peggiore**. È la scelta
-- prudente: una soglia («almeno tre celle sopra Moderato») ridurrebbe il
-- rumore ma nasconderebbe il versante singolo sopra un abitato, che è
-- esattamente il caso per cui questo sistema esiste. Il numero di celle sta
-- accanto, ed è quello che distingue un comune con una cella da uno con
-- quaranta.

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
    -- L'esposizione la porta il breakdown delle frane (`factors->>'e'`), e
    -- gli altri pericoli non hanno quel campo: per loro resta zero invece di
    -- fallire. È una classifica in meno, non una riga sbagliata.
    COALESCE(
        sum((m.factors ->> 'e')::double precision)
            FILTER (WHERE m.class IN ('High', 'VeryHigh')),
        0::double precision
    )                                                           AS exposure_rank,
    max(m.computed_at)                                          AS computed_at,
    c.geom,
    c.centroid
FROM comuni c
CROSS JOIN (SELECT hazard FROM hazards WHERE enabled) h
LEFT JOIN cell_comune cc ON cc.istat_code = c.istat_code
-- `latest_risk` e non `mv_latest_risk` (#125): è la stessa cosa senza il
-- giro attraverso la vista e il CROSS JOIN con i pericoli, che qui è già
-- fatto sopra.
LEFT JOIN latest_risk m
       ON m.cell_id = cc.cell_id
      AND m.hazard_type = h.hazard
      AND m.score IS NOT NULL
GROUP BY c.istat_code, c.name, c.aoi_id, h.hazard, c.geom, c.centroid
WITH NO DATA;

-- La chiave è la coppia: serve al REFRESH CONCURRENTLY, che senza un indice
-- unico non è possibile.
CREATE UNIQUE INDEX mv_comune_risk_pk ON mv_comune_risk (istat_code, hazard_type);
CREATE INDEX mv_comune_risk_geom_gix  ON mv_comune_risk USING gist (geom);
CREATE INDEX mv_comune_risk_aoi_idx   ON mv_comune_risk (aoi_id);
CREATE INDEX mv_comune_risk_hazard_idx ON mv_comune_risk (hazard_type, worst_class);

REFRESH MATERIALIZED VIEW mv_comune_risk;

-- ---------------------------------------------------------------------------
-- Il livello del comune sulla mappa: una riga sola per comune
-- ---------------------------------------------------------------------------
-- Con tre righe per comune pg_tileserv disegnerebbe tre poligoni sovrapposti
-- e il colore sarebbe quello dell'ultimo disegnato, cioè un caso. La mappa
-- vuole il peggiore dei tre, e vuole sapere **quale** per poterlo dire.
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
                        -- Spareggio sul nome del pericolo: senza, due
                        -- pericoli a pari classe si alternerebbero fra un
                        -- refresh e l'altro e la mappa cambierebbe da sola.
                        m.hazard_type::text
           ) AS rn
    FROM mv_comune_risk m
)
SELECT istat_code,
       name,
       aoi_id,
       hazard_type AS worst_hazard,
       worst_class,
       max_score,
       n_cells,
       n_alert,
       geom,
       centroid
FROM ordinati
WHERE rn = 1;

COMMENT ON VIEW v_comune_tiles IS
    'Una riga per comune: classe del pericolo peggiore e quale. È la sorgente '
    'del livello comunale della mappa, che con il rollup per pericolo '
    'disegnerebbe altrimenti tre poligoni sovrapposti.';
