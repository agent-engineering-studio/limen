-- 064 — la spiegazione dell'AI vive per (regione, pericolo), non per cella.
--
-- Fino a qui `briefing_enrichment` attaccava il testo alle righe di uno sweep,
-- in `risk_assessments` e in `latest_risk`. Due difetti, visti il 6 ottobre
-- 2026 con zero spiegazioni scritte in ore di job:
--
--   * lo sweep orario scrive nello storico solo le celle cambiate (#135):
--     un giro in cui nessuna cella cambia non lascia righe, e il job trovava
--     «no rows» su ogni regione;
--   * `latest_risk` lo sweep lo riscrive per intero a ogni ora, `explanation`
--     compresa: una spiegazione scritta alle 12:05 spariva alle 13:00.
--
-- La spiegazione racconta una regione, quindi sta in una tabella sua, che lo
-- sweep non tocca. `ripiego` dice se il testo è quello deterministico perché
-- il modello non ha risposto: la SPA non deve attribuire all'AI un testo che
-- l'AI non ha scritto. Nessun numero qui dentro è autorevole: punteggi e
-- classi restano in `latest_risk`.

CREATE TABLE IF NOT EXISTS spiegazioni_regione (
    aoi_id      text        NOT NULL,
    hazard_type hazard_type NOT NULL,
    run_id      bigint      NOT NULL,
    livello     text        NOT NULL,
    scritta     timestamptz NOT NULL DEFAULT now(),
    modello     text        NOT NULL,
    ripiego     boolean     NOT NULL,
    testo       text        NOT NULL,
    analisi     jsonb,
    PRIMARY KEY (aoi_id, hazard_type)
);
