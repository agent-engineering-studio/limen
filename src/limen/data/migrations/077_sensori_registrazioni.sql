-- 077 — registrazione dei sensori dei cittadini senza login (#253, epic #247).
--
-- Il modulo pubblico di `#/sensori` non crea un dispositivo: scrive una
-- richiesta e manda una mail a chi cura il progetto, che la approva dalla CLI
-- (`limen sensore approva`). Approvare firma la CSR del dispositivo con la CA
-- dei sensori e crea il dispositivo al livello 0.
--
-- `sensori_registranti` è l'unico posto dove sta un dato personale, la mail:
-- serve a rispondere, a contare la quota e a cancellare su richiesta. Nessuna
-- API, MCP o A2A la legge. Cancellare un registrante cancella le sue
-- richieste e stacca i suoi dispositivi (che la CLI mette prima in
-- quarantena e revoca, e la cui posizione riporta al centroide della cella):
-- le misure restano, senza nessuno a cui ricondurle.
--
-- Il certificato firmato si scrive sulla richiesta appena emesso, prima del
-- dispositivo: è pubblico, e un `approva` ripetuto — anche dopo un errore a
-- metà — lo riusa invece di firmarne un altro. Note e foto viaggiano solo
-- nella mail all'operatore.

CREATE TABLE IF NOT EXISTS sensori_registranti (
    id         bigserial PRIMARY KEY,
    email      text NOT NULL,
    creato_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT sensori_registranti_email_key UNIQUE (email),
    CONSTRAINT sensori_registranti_email_chk CHECK (email = lower(email))
);

CREATE TABLE IF NOT EXISTS sensori_richieste (
    id              bigserial PRIMARY KEY,
    registrante_id  bigint NOT NULL REFERENCES sensori_registranti(id) ON DELETE CASCADE,
    device_id       text NOT NULL,
    device_type     text NOT NULL,
    -- Numeri e non geometria: pg_tileserv pubblica ogni tabella con una
    -- colonna geometrica, e questa è la posizione proposta da un privato.
    lon             double precision NOT NULL,
    lat             double precision NOT NULL,
    -- Come `sensor_devices.cell_id`: una cella cancellata stacca la richiesta,
    -- che tiene la posizione e ritrova la cella all'approvazione.
    cell_id         text REFERENCES grid_cells(id) ON DELETE SET NULL,
    csr             text NOT NULL,
    licenza         text NOT NULL,
    stato           text NOT NULL DEFAULT 'in_attesa',
    certificato     text,
    creata_at       timestamptz NOT NULL DEFAULT now(),
    decisa_at       timestamptz,
    CONSTRAINT sensori_richieste_stato_chk
        CHECK (stato IN ('in_attesa', 'approvata', 'respinta'))
);
CREATE INDEX IF NOT EXISTS sensori_richieste_registrante_idx
    ON sensori_richieste (registrante_id);
CREATE INDEX IF NOT EXISTS sensori_richieste_cell_idx
    ON sensori_richieste (cell_id);
-- Un id per volta: due richieste aperte per lo stesso dispositivo sono un
-- doppio invio, e una delle due firmerebbe un certificato orfano.
CREATE UNIQUE INDEX IF NOT EXISTS sensori_richieste_device_aperta_uniq
    ON sensori_richieste (device_id) WHERE stato = 'in_attesa';

ALTER TABLE sensor_devices
    ADD COLUMN IF NOT EXISTS registrante_id bigint
        REFERENCES sensori_registranti(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS sensor_devices_registrante_idx
    ON sensor_devices (registrante_id);
