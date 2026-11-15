-- Il carico: su quanti comuni-giorno Limen ha previsto ≥ Moderato, pericolo
-- per pericolo (`carico_repo.misura`, `limen verifiche-report`, #345). È il
-- numero che va letto accanto alla quota di eventi colti: prevedere Moderato
-- ovunque coglie tutto.
--
-- $1 dal:  inizio della finestra (NULL = da quando c'è lo storico)
-- $2 al:   fine della finestra (NULL = adesso)
-- $3 job:  l'id del job della previsione per cella (`JOB_FORECAST_HISTORY`)
--
-- Stessa definizione dell'evento colto (`anticipo.sql`): una corsa
-- previsionale che punta a quel giorno, su una cella del comune. Lo storico
-- tiene le righe previsionali solo da Moderato in su, quindi contarle è
-- contare i comuni-giorno sopra soglia. Il giorno è quello UTC del
-- momento-obiettivo, come le partizioni. Il carico è lordo: lo sfondo di un
-- comune che sta in Moderato tutti i giorni conta, perché è quello che la
-- mappa mostra.
--
-- Ogni filtro su risk_assessments porta computed_at (partizioni per giorno):
-- una corsa parte al più 72 ore prima del suo obiettivo, da cui le 80 ore.
WITH finestra AS (
    SELECT $1::timestamptz AS dal, coalesce($2::timestamptz, now()) AS al
),
sopra AS (
    SELECT DISTINCT
           ra.hazard_type AS hazard,
           cc.istat_code,
           ((ra.computed_at
             + make_interval(hours => ltrim(rtrim(ra.horizon, 'h'), '+')::int))
            AT TIME ZONE 'UTC')::date AS giorno
    FROM risk_assessments ra
    JOIN cell_comune_tutte cc ON cc.cell_id = ra.cell_id
    CROSS JOIN finestra f
    WHERE ra.horizon LIKE '+%'
      AND ra.class IN ('Moderate', 'High', 'VeryHigh')
      AND ra.computed_at <= f.al
      AND (f.dal IS NULL OR ra.computed_at >= f.dal - interval '80 hours')
),
-- I giorni-obiettivo che una corsa riuscita ha davvero guardato: senza, un
-- giorno in cui la previsione non ha girato conterebbe come un giorno calmo
-- e abbasserebbe il carico. Gli orizzonti sono quelli di
-- `limen-forecast-history` (+24/+48/+72 h). La riga di `job_runs` è una per
-- corsa, non per pericolo: un pericolo fallito dentro una corsa riuscita qui
-- non si vede, e i suoi giorni contano come valutati.
giorni_job AS (
    SELECT DISTINCT
           ((jr.started_at + make_interval(hours => h)) AT TIME ZONE 'UTC')::date AS giorno
    FROM job_runs jr
    CROSS JOIN unnest(ARRAY[24, 48, 72]) AS h
    CROSS JOIN finestra f
    WHERE jr.job_id = $3::text
      AND jr.status = 'ok'
      AND jr.started_at <= f.al
      AND (f.dal IS NULL OR jr.started_at >= f.dal - interval '80 hours')
),
giorni AS (
    SELECT h.hazard, g.giorno
    FROM hazards h CROSS JOIN giorni_job g
    WHERE h.enabled
    UNION
    SELECT hazard, giorno FROM sopra
),
-- Solo i giorni dentro la finestra, e mai il futuro: un obiettivo di domani
-- non è ancora un giorno in cui un evento poteva essere colto.
nella_finestra AS (
    SELECT g.hazard, g.giorno
    FROM giorni g CROSS JOIN finestra f
    WHERE g.giorno <= (f.al AT TIME ZONE 'UTC')::date
      AND (f.dal IS NULL OR g.giorno >= (f.dal AT TIME ZONE 'UTC')::date)
)
SELECT n.hazard::text AS hazard,
       count(*)::int AS giorni,
       min(n.giorno) AS dal_giorno,
       max(n.giorno) AS al_giorno,
       (SELECT count(DISTINCT istat_code) FROM cell_comune_tutte)::int AS comuni,
       (SELECT count(*) FROM sopra s JOIN nella_finestra x USING (hazard, giorno)
        WHERE s.hazard = n.hazard)::int AS comuni_giorno_sopra
FROM nella_finestra n
GROUP BY n.hazard
