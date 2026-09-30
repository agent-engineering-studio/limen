-- 057 — lo stato corrente della previsione, come `latest_risk` lo è dell'adesso.
--
-- La previsione per cella viveva solo in `risk_assessments`, partizionata per
-- giorno: per sapere cosa è previsto su un comune bisognava attraversare le
-- partizioni cella per cella. Misurato su Marzi (un comune piccolo): 755 ms.
-- Per i trenta comuni della colonna, a ogni apertura della pagina, fanno
-- venti secondi — e la colonna è il posto dove la previsione deve stare,
-- accanto al comune a cui si riferisce, non in un pannello a parte per
-- regione.
--
-- Una riga per (cella, pericolo, orizzonte): l'ultima corsa previsionale.
-- La scrive `persist_forecast_run` nello stesso passo in cui scrive lo
-- storico, e ci **cancella anche le celle scese sotto soglia** — lo storico
-- no, e una cella che ieri era prevista Moderata e oggi non più restava lì a
-- dire una cosa vecchia.
--
-- Come lo storico previsionale, tiene solo le celle **≥ Moderato**. L'assenza
-- di una riga, per un pericolo la cui corsa è avvenuta, vuol dire «previsto
-- sotto Moderato»: una risposta, non un vuoto.

CREATE TABLE IF NOT EXISTS latest_forecast (
    cell_id     text        NOT NULL,
    hazard_type hazard_type NOT NULL,
    horizon_h   integer     NOT NULL,
    score       double precision NOT NULL,
    class       text        NOT NULL,
    -- Quando è stata fatta la corsa, e il momento a cui si riferisce. Il
    -- secondo si scrive invece di ricavarlo: chi legge non deve sapere che
    -- `+48h` va sommato all'ora della corsa.
    run_at      timestamptz NOT NULL,
    target_at   timestamptz NOT NULL,
    PRIMARY KEY (cell_id, hazard_type, horizon_h)
);

CREATE INDEX IF NOT EXISTS latest_forecast_hazard_idx
    ON latest_forecast (hazard_type, horizon_h, score DESC);

-- Popolamento dall'ultima corsa già scritta, così la colonna ha una
-- previsione da subito e non dalla prossima notte. Solo le ultime 36 ore:
-- oltre, la corsa è vecchia di un giorno e mezzo e mostrarla come «prevista»
-- sarebbe peggio di non mostrarla.
INSERT INTO latest_forecast (cell_id, hazard_type, horizon_h, score, class, run_at, target_at)
SELECT DISTINCT ON (cell_id, hazard_type, horizon)
       cell_id,
       hazard_type,
       ltrim(rtrim(horizon, 'h'), '+')::int,
       score,
       class,
       computed_at,
       computed_at + make_interval(hours => ltrim(rtrim(horizon, 'h'), '+')::int)
FROM risk_assessments
WHERE horizon LIKE '+%'
  AND pipeline_version LIKE 'v1-forecast+%'
  AND computed_at >= now() - interval '36 hours'
  AND score IS NOT NULL
ORDER BY cell_id, hazard_type, horizon, computed_at DESC
ON CONFLICT (cell_id, hazard_type, horizon_h) DO NOTHING;
