-- 054 — «non misurato» arriva anche sulle tile (#143).
--
-- La 053 ha messo il flag su `latest_risk` e sul rollup per comune. Qui
-- entra nelle tre sorgenti che disegnano la mappa: la vista delle frane, la
-- vista d'insieme e le due funzioni che pg_tileserv serve per un pericolo
-- diverso dal predefinito.
--
-- Sulla mappa lo stato si disegna con lo **stesso grigio neutro** delle
-- celle non ancora valutate, e non con una sesta tinta. Le due cose dicono
-- la stessa cosa a chi guarda — «di qui non so niente» — e la scala del
-- rischio ha cinque classi proprio perché aggiungerne una sesta la rende
-- illeggibile. Il perché della differenza sta nel popup e nella colonna,
-- dove c'è lo spazio per scriverlo.
--
-- `COALESCE(measured, true)` ovunque: NULL è lo storico scritto prima che la
-- colonna esistesse, cioè «non lo sappiamo», e retro-marcarlo come non
-- misurato sarebbe inventare al contrario.

-- `CREATE OR REPLACE VIEW` ammette solo colonne **in coda**: `measured` va
-- dopo `geom` anche se si leggerebbe meglio prima. Il prezzo di non dover
-- ricreare a cascata le viste che dipendono da questa.
CREATE OR REPLACE VIEW v_risk_tiles AS
SELECT cell_id,
       aoi_id,
       risk_score,
       risk_level,
       computed_at,
       geom,
       COALESCE(measured, true) AS measured
FROM mv_latest_risk
WHERE hazard_type = 'landslide'::hazard_type;

CREATE OR REPLACE FUNCTION public.risk_at(z integer, x integer, y integer, hours_ago integer DEFAULT 0, p_hazard hazard_type DEFAULT 'landslide'::hazard_type)
 RETURNS bytea
 LANGUAGE plpgsql
 STABLE PARALLEL SAFE
AS $function$
DECLARE
    out bytea;
BEGIN
    IF GREATEST(hours_ago, 0) = 0 THEN
        -- «Adesso»: lo stato corrente è una riga per cella, e sta già lì.
        WITH bounds AS (
            SELECT ST_TileEnvelope(z, x, y) AS b
        ),
        cells AS (
            SELECT g.id, g.geom
            FROM grid_cells g, bounds
            -- Il confronto avviene in 4326, cioè nel sistema in cui le
            -- geometrie sono memorizzate e in cui esiste l'indice GIST:
            -- trasformare la colonna rende l'espressione non indicizzabile e
            -- obbliga a leggere tutte le 312.550 celle per ogni tile. Si
            -- trasforma il riquadro, che è una geometria sola.
            WHERE g.geom && ST_Transform(bounds.b, 4326)
        ),
        mvt AS (
            SELECT ST_AsMVTGeom(ST_Transform(c.geom, 3857), bounds.b) AS geom,
                   c.id      AS cell_id,
                   lr.score  AS risk_score,
                   lr.class  AS risk_level,
                   -- Falso ⇒ la cella si disegna neutra, non in fondo alla
                   -- scala: zero per assenza di misura non è zero per quiete
                   -- (#143). NULL sullo storico vale «non lo sappiamo», che
                   -- si legge come misurato.
                   COALESCE(lr.measured, true) AS measured
            FROM cells c
            JOIN latest_risk lr
              ON lr.cell_id = c.id AND lr.hazard_type = p_hazard, bounds
        )
        SELECT ST_AsMVT(mvt.*, 'public.v_risk_tiles', 4096, 'geom' ORDER BY mvt.cell_id)
        INTO out FROM mvt;
    ELSE
        -- «N ore fa»: qui la domanda è storica e lo storico va attraversato,
        -- ma solo per le celle di questa tile. Con la scrittura selettiva del
        -- #135 questo ramo è anche più corretto di prima: prende l'ultima
        -- riga **fino a** quell'istante, che è lo stato di allora anche
        -- quando nel frattempo non era cambiato niente.
        WITH bounds AS (
            SELECT ST_TileEnvelope(z, x, y) AS b
        ),
        cells AS (
            SELECT g.id, g.geom
            FROM grid_cells g, bounds
            WHERE g.geom && ST_Transform(bounds.b, 4326)
        ),
        latest AS (
            SELECT DISTINCT ON (ra.cell_id) ra.cell_id, ra.score, ra.class,
                   COALESCE(ra.measured, true) AS measured
            FROM risk_assessments ra
            JOIN cells c ON c.id = ra.cell_id
            WHERE ra.hazard_type = p_hazard
              AND ra.computed_at <= now() - make_interval(hours => hours_ago)
              -- Lo sguardo indietro è limitato, e la #135 è ciò che lo rende
              -- corretto: il battito garantisce almeno una riga per cella
              -- ogni 24 ore, quindi in due giorni ogni cella ne ha una di
              -- sicuro. Senza il limite la ricerca attraversa tutte le
              -- partizioni esistenti — misurato con 110 partizioni: 85
              -- secondi contro 4. Se qualcuno alza
              -- `SCORING__HISTORY_HEARTBEAT_HOURS` oltre le 24 ore, questa
              -- finestra va allargata con lui, altrimenti le celle immobili
              -- spariscono dalla mappa del passato.
              AND ra.computed_at >= now() - make_interval(hours => hours_ago) - interval '48 hours'
            ORDER BY ra.cell_id, ra.computed_at DESC
        ),
        mvt AS (
            SELECT ST_AsMVTGeom(ST_Transform(c.geom, 3857), bounds.b) AS geom,
                   c.id      AS cell_id,
                   l.score   AS risk_score,
                   l.class   AS risk_level,
                   l.measured AS measured
            FROM cells c
            JOIN latest l ON l.cell_id = c.id, bounds
        )
        SELECT ST_AsMVT(mvt.*, 'public.v_risk_tiles', 4096, 'geom' ORDER BY mvt.cell_id)
        INTO out FROM mvt;
    END IF;
    RETURN out;
END $function$;

CREATE OR REPLACE FUNCTION public.multi_hazard_at(z integer, x integer, y integer)
 RETURNS bytea
 LANGUAGE sql
 STABLE PARALLEL SAFE
AS $function$
WITH bounds AS (
    SELECT ST_TileEnvelope(z, x, y) AS b
),
cells AS (
    SELECT g.id, g.geom
    FROM grid_cells g, bounds
    -- Il confronto avviene in 4326, cioè nel sistema in cui le geometrie
    -- sono memorizzate e in cui esiste l'indice GIST: trasformare la colonna
    -- (`ST_Transform(g.geom, 3857) && ...`) rende l'espressione non
    -- indicizzabile e obbliga a leggere tutte le 312.550 celle per ogni
    -- tile. Misurato: 1,5 s contro i ~100 ms della vista delle frane, che
    -- pg_tileserv interroga proprio così. Si trasforma il riquadro, che è
    -- una geometria sola.
    WHERE g.geom && ST_Transform(bounds.b, 4326)
),
per_cella AS (
    SELECT lr.cell_id,
           lr.hazard_type,
           lr.score,
           lr.class,
           COALESCE(lr.measured, true) AS measured,
           row_number() OVER (
               PARTITION BY lr.cell_id
               ORDER BY CASE WHEN COALESCE(lr.measured, true) THEN 0 ELSE 1 END,
                        CASE lr.class
                            WHEN 'VeryHigh' THEN 4
                            WHEN 'High'     THEN 3
                            WHEN 'Moderate' THEN 2
                            WHEN 'Low'      THEN 1
                            ELSE 0
                        END DESC,
                        lr.score DESC NULLS LAST,
                        -- Spareggio sul nome: senza, due pericoli a pari
                        -- classe e pari punteggio si alternerebbero fra una
                        -- tile e l'altra e la mappa sembrerebbe cambiare
                        -- senza motivo.
                        lr.hazard_type::text
           ) AS rn,
           count(*) FILTER (WHERE lr.class IS NOT NULL)
               OVER (PARTITION BY lr.cell_id) AS hazards_scored,
           -- L'ordine deterministico lo dà la finestra, non l'aggregato:
           -- `array_agg(... ORDER BY ...) OVER (...)` non è ammesso, e senza
           -- un ordine l'elenco dei pericoli cambierebbe fra una tile e
           -- l'altra.
           array_agg(lr.hazard_type::text)
               FILTER (WHERE lr.class IN ('High', 'VeryHigh'))
               OVER (
                   PARTITION BY lr.cell_id
                   ORDER BY lr.hazard_type::text
                   ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
               ) AS hazards_at_high
    FROM latest_risk lr
    JOIN cells c ON c.id = lr.cell_id
),
mvt AS (
    SELECT ST_AsMVTGeom(ST_Transform(c.geom, 3857), bounds.b) AS geom,
           p.cell_id,
           p.hazard_type::text AS worst_hazard,
           p.class             AS worst_level,
           p.score             AS worst_score,
           p.measured,
           p.hazards_scored,
           array_to_string(p.hazards_at_high, ',') AS hazards_at_high
    FROM per_cella p
    JOIN cells c ON c.id = p.cell_id, bounds
    WHERE p.rn = 1 AND p.class IS NOT NULL
)
SELECT ST_AsMVT(mvt.*, 'public.v_multi_hazard', 4096, 'geom' ORDER BY mvt.cell_id)
FROM mvt;
$function$;
