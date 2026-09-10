-- 046_job_runs.sql
--
-- Ogni job periodico lascia una riga: inizio, fine, esito, metriche (#75).
--
-- Prima di questa tabella la durata di uno sweep si ricavava **solo** dai log
-- del container, e non si sapeva quando fosse finito l'ultimo né quanto
-- avesse messo. È il passo 1 dell'epic #74 proprio per questo: i passi
-- successivi — vettorizzazione, worker separato, cadenze — vanno misurati, e
-- senza un baseline si ottimizza a intuito.
--
-- `scope` è l'AOI per lo sweep, NULL per i job globali: così una riga dice
-- "lo sweep nazionale è durato N" e venti righe dicono quale regione l'ha
-- fatto durare. È l'informazione che manca oggi.
--
-- `host` distingue il processo: dopo lo split api/worker (#77) la stessa
-- tabella riceve righe da due container, e sapere quale le ha scritte è
-- l'unico modo di accorgersi che lo scheduler gira ancora dentro l'API.
--
-- `status = 'skipped'` non è un errore: lo sweep orario salta il tick quando
-- il precedente è ancora in corso, ed è un comportamento voluto. Registrarlo
-- come errore renderebbe illeggibile il tasso di errore; non registrarlo
-- nasconderebbe il fatto che il sistema è in ritardo su se stesso.

CREATE TABLE IF NOT EXISTS job_runs (
    id           bigserial   PRIMARY KEY,
    job_id       text        NOT NULL,
    scope        text,
    started_at   timestamptz NOT NULL DEFAULT now(),
    finished_at  timestamptz,
    status       text        NOT NULL DEFAULT 'running',
    metrics      jsonb       NOT NULL DEFAULT '{}'::jsonb,
    error        text,
    host         text        NOT NULL,
    CONSTRAINT job_runs_status_check
        CHECK (status IN ('running', 'ok', 'error', 'skipped'))
);

CREATE INDEX IF NOT EXISTS job_runs_job_started_idx
    ON job_runs (job_id, started_at DESC);

CREATE INDEX IF NOT EXISTS job_runs_scope_started_idx
    ON job_runs (scope, started_at DESC)
    WHERE scope IS NOT NULL;
