-- 039_alert_governance.sql
--
-- Governo degli alert (issue #59). Tre pericoli su ~312.000 celle: un fronte
-- temporalesco esteso porta migliaia di celle sopra soglia nello stesso
-- ciclo, e la dedup per (cella, pericolo) non protegge un destinatario umano.
--
-- Due tabelle, due scopi distinti che è sbagliato mescolare:
--
-- `alert_aggregates` è **il rollup comunale, e la coda del digest**. Una riga
-- per (comune, pericolo) per ciclo, con lo stato: `sent` se è uscita subito,
-- `queued` se il rate limit l'ha trattenuta. Tenerle nella stessa tabella e
-- non in una coda separata è deliberato: la voce accodata *è* l'aggregato,
-- e duplicarla in due tabelle vorrebbe dire tenerle in accordo.
--
-- `notification_sends` conta le **uscite per canale**, che è l'unica cosa su
-- cui un limite orario possa essere misurato. `alert_dispatches.channels` è
-- per cella: con 400 celle in un messaggio conterebbe 400 invii dove ce n'è
-- stato uno.
--
-- `alert_dispatches` resta com'è: la cella rimane consultabile nel dettaglio,
-- e il rollup non sostituisce la tracciabilità per cella.

CREATE TABLE IF NOT EXISTS alert_aggregates (
    id             bigserial PRIMARY KEY,
    -- NULL quando la cella non ha ancora un comune in `cell_comune`: quelle
    -- celle esistono e vanno nominate comunque.
    istat_code     text,
    comune         text,
    aoi_id         text NOT NULL,
    hazard_type    hazard_type NOT NULL,
    max_level      text NOT NULL,
    max_score      double precision NOT NULL,
    cells_count    integer NOT NULL CHECK (cells_count > 0),
    top_cells      jsonb NOT NULL DEFAULT '[]'::jsonb,
    state          text NOT NULL CHECK (state IN ('sent', 'queued', 'expired')),
    created_at     timestamptz NOT NULL DEFAULT now(),
    sent_at        timestamptz,
    -- Il lotto del digest che l'ha spedita, per risalire da un riepilogo alle
    -- righe che lo componevano.
    digest_id      text,
    channels       jsonb NOT NULL DEFAULT '{}'::jsonb
);

-- Dedup per (comune, pericolo, finestra): è la query calda del percorso.
CREATE INDEX IF NOT EXISTS alert_aggregates_dedup_idx
    ON alert_aggregates (istat_code, hazard_type, created_at DESC);
-- Scansione della coda: parziale, perché le righe già spedite sono la
-- maggioranza e non interessano mai a chi svuota la coda.
CREATE INDEX IF NOT EXISTS alert_aggregates_queue_idx
    ON alert_aggregates (created_at)
    WHERE state = 'queued';
CREATE INDEX IF NOT EXISTS alert_aggregates_aoi_idx
    ON alert_aggregates (aoi_id, created_at DESC);

CREATE TABLE IF NOT EXISTS notification_sends (
    id          bigserial PRIMARY KEY,
    channel     text NOT NULL,
    -- 'alert' = messaggio immediato, 'digest' = riepilogo della coda.
    kind        text NOT NULL CHECK (kind IN ('alert', 'digest')),
    ok          boolean NOT NULL,
    aggregates  integer NOT NULL DEFAULT 0,
    sent_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS notification_sends_channel_idx
    ON notification_sends (channel, sent_at DESC);

COMMENT ON TABLE alert_aggregates IS
    'Rollup comunale degli alert e coda del digest (#59). state: sent | queued | expired.';
COMMENT ON TABLE notification_sends IS
    'Un record per messaggio uscito da un canale (#59) — la base del rate limit orario.';
