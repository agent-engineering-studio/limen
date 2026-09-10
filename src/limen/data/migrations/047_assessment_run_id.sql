-- 047_assessment_run_id.sql
--
-- Un identificatore per **sweep**, non per riga (#76).
--
-- Prima, `MonitoringContext.assessment_id` era il `RETURNING id` dell'ultima
-- INSERT del ciclo: identificava una cella arbitraria — l'ultima capitata —
-- e non la valutazione. Chi lo leggeva nei log o nella risposta MCP voleva
-- sapere *quale sweep* aveva prodotto quei numeri, e riceveva il numero di
-- riga di una cella qualunque.
--
-- Con la persistenza via COPY il `RETURNING` non esiste più, quindi la
-- domanda va risolta invece che aggirata: una sequenza dedicata dà un id per
-- sweep, scritto su ogni riga di quello sweep. Ora
-- `WHERE run_id = X` restituisce esattamente le righe di una valutazione.
--
-- Sequenza e non `job_runs.id`: `limen monitor-once` non crea una riga di
-- job — è un comando manuale, non un job periodico — e legare la persistenza
-- alla tracciatura dei job significherebbe che una valutazione a mano non ha
-- identificatore. La sequenza è autosufficiente.
--
-- Nullable: le righe già scritte non hanno un run_id e non se ne può
-- inventare uno. NULL qui significa "scritta prima che l'identificatore
-- esistesse", che è un fatto, non un dato mancante.

CREATE SEQUENCE IF NOT EXISTS assessment_run_id_seq AS bigint;

ALTER TABLE risk_assessments
    ADD COLUMN IF NOT EXISTS run_id bigint;

COMMENT ON COLUMN risk_assessments.run_id IS
    'Sweep che ha prodotto la riga (assessment_run_id_seq). NULL = pre-#76.';

CREATE INDEX IF NOT EXISTS risk_assessments_run_idx
    ON risk_assessments (run_id, computed_at)
    WHERE run_id IS NOT NULL;
