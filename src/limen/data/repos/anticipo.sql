-- Quanto prima Limen ha visto un evento: un oggetto JSON (`anticipo_repo.misura`,
-- `limen anticipo`).
--
-- $1 istat:    i codici ISTAT dei comuni dell'evento
-- $2 hazard:   landslide | flood | wildfire
-- $3 event_at: quando è successo
-- $4 tol:      ore di tolleranza attorno all'evento per dire «la previsione
--              puntava lì» (12 = la stessa mezza giornata)
--
-- Ogni filtro su risk_assessments porta computed_at: è partizionata per
-- giorno, e senza la finestra la query attraversa tutte le partizioni (su
-- questo disco: minuti invece di secondi).
WITH ev AS (
    SELECT $3::timestamptz AS t, make_interval(hours => $4::int) AS tol
),
celle AS (
    SELECT DISTINCT cell_id FROM cell_comune_tutte
    WHERE istat_code = ANY ($1::text[])
),
-- Le corse previsionali (+24/+48/+72 h) il cui momento-obiettivo cade
-- nell'intorno dell'evento. Lo storico tiene solo le celle ≥ Moderato:
-- nessuna riga = previsto sotto Moderato, non «non calcolato».
previste AS (
    SELECT ra.computed_at AS run_at,
           ltrim(rtrim(ra.horizon, 'h'), '+')::int AS horizon_h,
           ra.cell_id, ra.score, ra.class, ra.factors
    FROM risk_assessments ra, ev
    WHERE ra.hazard_type = $2::hazard_type
      AND ra.horizon LIKE '+%'
      AND ra.computed_at BETWEEN ev.t - interval '80 hours' - ev.tol AND ev.t
      AND ra.cell_id IN (SELECT cell_id FROM celle)
      AND ra.computed_at + make_interval(hours => ltrim(rtrim(ra.horizon, 'h'), '+')::int)
          BETWEEN ev.t - ev.tol AND ev.t + ev.tol
),
corse AS (
    SELECT DISTINCT ON (run_at, horizon_h)
           run_at, horizon_h, score, class, factors, cell_id,
           count(*) OVER (PARTITION BY run_at, horizon_h) AS celle_sopra_soglia
    FROM previste
    ORDER BY run_at, horizon_h, score DESC
),
-- Lo sweep orario (horizon '24h'): cosa diceva Limen «adesso» prima e
-- durante l'evento. Scrittura sparsa (#135): una riga solo a cambio classe.
osservate AS (
    SELECT ra.computed_at, ra.cell_id, ra.score, ra.class, ra.measured, ra.factors
    FROM risk_assessments ra, ev
    WHERE ra.hazard_type = $2::hazard_type
      AND ra.horizon = '24h'
      AND ra.computed_at BETWEEN ev.t - interval '72 hours' AND ev.t + interval '6 hours'
      AND ra.cell_id IN (SELECT cell_id FROM celle)
),
-- La classe di fondo del comune, da 10 a 4 giorni prima: dove il terreno
-- tiene una cella in Moderato tutti i giorni, una previsione Moderata non è
-- un segnale, è lo sfondo.
fondo AS (
    SELECT ra.computed_at, ra.class, ra.score
    FROM risk_assessments ra, ev
    WHERE ra.hazard_type = $2::hazard_type
      AND ra.horizon = '24h'
      AND ra.computed_at BETWEEN ev.t - interval '10 days' AND ev.t - interval '4 days'
      AND ra.cell_id IN (SELECT cell_id FROM celle)
),
ordine(class, rango) AS (
    VALUES ('None', 0), ('Low', 1), ('Moderate', 2), ('High', 3), ('VeryHigh', 4)
)
SELECT json_build_object(
    'evento', (SELECT t FROM ev),
    'celle', (SELECT count(*) FROM celle),
    -- Oltre la retention (ASSESSMENTS_RETENTION_DAYS, 14 giorni) lo storico
    -- non c'è più: «nessuna riga» lì vuol dire «non verificabile».
    'storico_dal', (SELECT min(computed_at) FROM risk_assessments
                    WHERE hazard_type = $2::hazard_type AND horizon = '+24h'),
    -- La retention cancella per partizione (un giorno UTC): la più vecchia
    -- rimasta dice da quando c'è ancora tutto, righe del fondo comprese. Le
    -- righe `+24h` no: si scrivono solo da Moderato in su, e la loro assenza
    -- è un fondo basso, non uno storico cancellato.
    'partizioni_dal', (SELECT min(to_date(right(c.relname, 8), 'YYYYMMDD'))
                       FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid
                       WHERE i.inhparent = 'public.risk_assessments'::regclass
                         AND c.relname ~ '^risk_assessments_[0-9]{8}$'),
    'anticipo_ore_moderato', (
        SELECT round(extract(epoch FROM (SELECT t FROM ev) - min(run_at)) / 3600)
        FROM corse),
    'anticipo_ore_alto', (
        SELECT round(extract(epoch FROM (SELECT t FROM ev) - min(run_at)) / 3600)
        FROM corse WHERE class IN ('High', 'VeryHigh')),
    'classe_prevista_max', (
        SELECT c.class FROM corse c JOIN ordine o USING (class)
        ORDER BY o.rango DESC, c.score DESC LIMIT 1),
    'fondo_classe_max', (
        SELECT f.class FROM fondo f JOIN ordine o USING (class)
        ORDER BY o.rango DESC, f.score DESC LIMIT 1),
    'fondo_giorni_moderato', (
        SELECT count(DISTINCT computed_at::date) FROM fondo
        WHERE class IN ('Moderate', 'High', 'VeryHigh')),
    'corse', COALESCE((
        SELECT json_agg(json_build_object(
                   'run_at', run_at, 'horizon_h', horizon_h,
                   'target_at', run_at + make_interval(hours => horizon_h),
                   'classe', class, 'score', round(score::numeric, 3),
                   'celle_sopra_soglia', celle_sopra_soglia,
                   'cella', cell_id, 'fattori', factors)
               ORDER BY run_at)
        FROM corse), '[]'::json),
    'adesso_primo_moderato', (
        SELECT min(computed_at) FROM osservate
        WHERE class IN ('Moderate', 'High', 'VeryHigh')),
    'adesso_classe_max', (
        SELECT o.class FROM osservate o JOIN ordine r USING (class)
        WHERE o.computed_at <= (SELECT t FROM ev)
        ORDER BY r.rango DESC, o.score DESC LIMIT 1),
    -- Il pericolo ha girato davvero nei giorni prima? Lo storico più vecchio
    -- (`storico_dal`) non lo dice: un job fermo da tre giorni lascia l'evento
    -- senza valutazione, e «non valutato» non è «mancato».
    'pericolo_valutato', EXISTS (
        SELECT 1 FROM risk_assessments ra, ev
        WHERE ra.hazard_type = $2::hazard_type
          AND ra.computed_at BETWEEN ev.t - interval '80 hours' AND ev.t
    ),
    -- Solo le ore prima dell'evento: un dato tornato dopo non dice niente su
    -- quello che Limen vedeva prima.
    'adesso_misurato', (
        SELECT count(*) FROM osservate
        WHERE measured IS NOT FALSE AND computed_at <= (SELECT t FROM ev)),
    'adesso_non_misurato', (
        SELECT count(*) FROM osservate
        WHERE measured IS FALSE AND computed_at <= (SELECT t FROM ev)),
    'adesso_picco', (
        SELECT json_build_object('t', computed_at, 'classe', class,
                                 'score', round(score::numeric, 3),
                                 'cella', cell_id, 'fattori', factors)
        FROM osservate WHERE computed_at <= (SELECT t FROM ev)
        ORDER BY score DESC LIMIT 1),
    -- Gli alert davvero spediti: uno per cella, quindi riassunti.
    'allerte', (
        SELECT json_build_object('prima', min(dispatched_at), 'celle', count(DISTINCT cell_id),
                                 'livelli', array_agg(DISTINCT level))
        FROM alert_dispatches ad, ev
        WHERE ad.hazard_type = $2::hazard_type
          AND ad.cell_id IN (SELECT cell_id FROM celle)
          AND ad.dispatched_at BETWEEN ev.t - interval '72 hours' AND ev.t + interval '6 hours'
        HAVING count(*) > 0)
)
