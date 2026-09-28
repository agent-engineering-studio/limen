-- 050 — le tile di tutti i pericoli leggono lo stato corrente, non lo storico.
--
-- IL FATTO. Il selettore in alto mostrava i tre pericoli ma non disegnava
-- nessuna cella per due di essi. Non era un difetto del frontend: le frane
-- passano da `v_risk_tiles`, una vista su `latest_risk` che risponde in ~100
-- ms, mentre alluvione e incendio passavano da `risk_at()` e il quadro
-- unico da `multi_hazard_at()`, rimaste sullo schema di prima del #125.
--
-- `risk_at()` faceva un DISTINCT ON su `risk_assessments` — 180 GB di
-- storico — per **ogni singola tile**: misurati oltre 120 secondi per una,
-- poi il timeout. `multi_hazard_at()` ha lo stesso difetto in altra forma:
-- classificava tutte le 937.000 righe e solo dopo filtrava il riquadro.
--
-- LA CORREZIONE. Due cose, una per funzione.
--
-- In `risk_at()` il caso normale — `hours_ago = 0`, cioè «adesso», che è
-- quello che la mappa chiede sempre tranne quando si trascina il cursore
-- del tempo — legge `latest_risk`: una riga per cella, già filtrata dal
-- riquadro. Il ramo storico resta per `hours_ago > 0`, dove la domanda è
-- davvero storica e lo storico va attraversato. Con la scrittura selettiva
-- del #135 quel ramo è anche più corretto di prima: prende l'ultima riga
-- **fino a** quell'istante, che è lo stato di allora anche quando nel
-- frattempo non era cambiato niente.
--
-- In `multi_hazard_at()` le celle del riquadro si scelgono **prima** di
-- classificarle. Era l'ordine sbagliato: la finestra di ordinamento girava
-- su tutta Italia per restituire le poche centinaia di celle di una tile.

-- PL/pgSQL e non SQL: i due rami vanno **pianificati separatamente**. In una
-- funzione SQL `hours_ago` è un parametro, quindi la UNION con il ramo
-- storico entra comunque nel piano e costa anche quando il filtro a tempo di
-- esecuzione lo scarta — misurato: 1 secondo a tile contro i 22 millisecondi
-- della stessa query scritta a mano. Con l'IF si pianifica solo il ramo che
-- serve.
CREATE OR REPLACE FUNCTION public.risk_at(
    z integer, x integer, y integer,
    hours_ago integer DEFAULT 0,
    p_hazard hazard_type DEFAULT 'landslide'::hazard_type
) RETURNS bytea AS $$
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
                   lr.class  AS risk_level
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
            SELECT DISTINCT ON (ra.cell_id) ra.cell_id, ra.score, ra.class
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
                   l.class   AS risk_level
            FROM cells c
            JOIN latest l ON l.cell_id = c.id, bounds
        )
        SELECT ST_AsMVT(mvt.*, 'public.v_risk_tiles', 4096, 'geom' ORDER BY mvt.cell_id)
        INTO out FROM mvt;
    END IF;
    RETURN out;
END $$ LANGUAGE plpgsql STABLE PARALLEL SAFE;

COMMENT ON FUNCTION public.risk_at IS
    'Tile di un pericolo. `hours_ago = 0` legge lo stato corrente da '
    'latest_risk (#125); oltre lo zero attraversa lo storico, che è dove '
    'quella domanda ha risposta. Il layer MVT si chiama public.v_risk_tiles.';

-- ---------------------------------------------------------------------------
-- Quadro unico: prima si sceglie il riquadro, poi si classifica
-- ---------------------------------------------------------------------------
-- Non usa più `v_multi_hazard`, che resta per chi legge tutta l'Italia (le
-- API e i conteggi): una vista con una finestra di ordinamento non si lascia
-- spingere dentro il filtro spaziale, e per una tile è il costo sbagliato.
CREATE OR REPLACE FUNCTION public.multi_hazard_at(
    z integer, x integer, y integer
) RETURNS bytea AS $$
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
           row_number() OVER (
               PARTITION BY lr.cell_id
               ORDER BY CASE lr.class
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
           p.hazards_scored,
           array_to_string(p.hazards_at_high, ',') AS hazards_at_high
    FROM per_cella p
    JOIN cells c ON c.id = p.cell_id, bounds
    WHERE p.rn = 1 AND p.class IS NOT NULL
)
SELECT ST_AsMVT(mvt.*, 'public.v_multi_hazard', 4096, 'geom' ORDER BY mvt.cell_id)
FROM mvt;
$$ LANGUAGE sql STABLE PARALLEL SAFE;

COMMENT ON FUNCTION public.multi_hazard_at IS
    'Tile del quadro unico (#58), sullo stato corrente e filtrata per '
    'riquadro prima di classificare. Il layer MVT si chiama '
    'public.v_multi_hazard.';
