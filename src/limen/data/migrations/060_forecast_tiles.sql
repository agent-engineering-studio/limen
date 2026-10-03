-- 060 — la previsione sulla mappa: una tile per orizzonte (#155, fase 3).
--
-- La timeline della mappa (Ora / +24 / +48 / +72 h) chiede, per ogni cella
-- del riquadro, la classe prevista a quell'orizzonte. La risposta sta già in
-- `latest_forecast`: una riga per (cella, pericolo, orizzonte), l'ultima
-- corsa, solo le celle **≥ Moderato**. Una cella senza riga è prevista sotto
-- Moderato per i pericoli la cui corsa è avvenuta; per gli altri — oggi
-- l'alluvione, prevista solo per comune — non si sa, e la mappa lo dice a
-- parole, non con un colore.
--
-- `p_hazard` NULL è la vista d'insieme: la classe peggiore fra i pericoli
-- previsti, con lo stesso spareggio di `multi_hazard_at()` (classe, poi
-- punteggio, poi nome) perché la cella non cambi colore fra una tile e
-- l'altra. Testo e non `hazard_type`: pg_tileserv passa i parametri dalla
-- query string, e un valore sconosciuto deve dare una tile vuota, non un
-- errore di cast a ogni richiesta.
--
-- Il layer porta sia `risk_level` sia `worst_level`: la mappa colora con il
-- primo e disegna il bordo «quale pericolo» con il secondo, come nelle due
-- sorgenti dell'adesso. `measured` è sempre vero: una riga previsionale
-- esiste solo se il calcolo è avvenuto.

-- PL/pgSQL con `EXECUTE` e non SQL: in una funzione SQL i parametri entrano
-- nel piano come valori sconosciuti, e il piano generico che ne esce a zoom 7
-- misurava 68 secondi a tile contro i 0,4 della stessa query scritta a mano.
-- `EXECUTE ... USING` pianifica ogni chiamata con i valori veri.
CREATE OR REPLACE FUNCTION public.forecast_at(
    z integer, x integer, y integer,
    p_horizon integer DEFAULT 24,
    p_hazard text DEFAULT NULL
) RETURNS bytea
 LANGUAGE plpgsql
 STABLE PARALLEL SAFE
AS $function$
DECLARE
    out bytea;
BEGIN
    EXECUTE $q$
    WITH bounds AS (
        SELECT ST_TileEnvelope($1, $2, $3) AS b
    ),
    cells AS (
        -- Il riquadro in 4326, dove c'è l'indice: vedi `multi_hazard_at()`.
        SELECT g.id, g.geom
        FROM grid_cells g, bounds
        WHERE g.geom && ST_Transform(bounds.b, 4326)
    ),
    per_cella AS (
        -- La geometria viaggia con la riga: un secondo join con `cells` dopo
        -- la finestra diventava un ciclo annidato da 14.000 × 38.000
        -- confronti, 98 secondi per una tile a zoom 7.
        SELECT lf.cell_id,
               c.geom,
               lf.hazard_type::text AS hazard,
               lf.score,
               lf.class,
               lf.target_at,
               row_number() OVER (
                   PARTITION BY lf.cell_id
                   ORDER BY CASE lf.class
                                WHEN 'VeryHigh' THEN 4
                                WHEN 'High'     THEN 3
                                WHEN 'Moderate' THEN 2
                                WHEN 'Low'      THEN 1
                                ELSE 0
                            END DESC,
                            lf.score DESC,
                            lf.hazard_type::text
               ) AS rn
        FROM latest_forecast lf
        JOIN cells c ON c.id = lf.cell_id
        WHERE lf.horizon_h = $4
          AND ($5::text IS NULL OR lf.hazard_type::text = $5::text)
    ),
    mvt AS (
        SELECT ST_AsMVTGeom(ST_Transform(p.geom, 3857), bounds.b) AS geom,
               p.cell_id,
               p.score       AS risk_score,
               p.class       AS risk_level,
               p.class       AS worst_level,
               p.hazard      AS worst_hazard,
               true          AS measured,
               p.target_at::text AS target_at
        FROM per_cella p, bounds
        WHERE p.rn = 1
    )
    SELECT ST_AsMVT(mvt.*, 'public.v_forecast_tiles', 4096, 'geom' ORDER BY mvt.cell_id)
    FROM mvt
    $q$
    INTO out
    USING z, x, y, p_horizon, p_hazard;
    RETURN out;
END $function$;

COMMENT ON FUNCTION public.forecast_at(integer, integer, integer, integer, text) IS
    'Tile della previsione per cella a un orizzonte (24/48/72 h), da latest_forecast. '
    'p_hazard NULL = il peggiore fra i pericoli previsti. Solo celle >= Moderato.';
