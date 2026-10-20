-- 082 — sensori LoRaWAN via il webhook di The Things Network (#266, epic #247).
--
-- Un dispositivo LoRaWAN non ha una CSR: lo identifica il DevEUI, e TTN
-- consegna i suoi uplink a un webhook che è dell'applicazione TTN, non del
-- dispositivo. Ogni registrante ha la sua applicazione: il webhook si
-- autentica con un segreto di quell'applicazione, generato da
-- `limen sensore approva` e mandato una volta per mail. Qui ne resta solo lo
-- SHA-256 — il segreto è casuale a 256 bit, non serve un hash lento — e un
-- segreto vale solo per i dispositivi della sua applicazione.
--
-- Nessuna colonna geometry, e nessun GRANT a `limen_tiles`: pg_tileserv non
-- la vede (#269).

CREATE TABLE IF NOT EXISTS sensori_ttn (
    -- L'id dell'applicazione su The Things Stack: minuscole, cifre, trattini.
    applicazione    text PRIMARY KEY,
    -- Cancellare il registrante cancella l'applicazione, e i suoi dispositivi
    -- smettono di poter parlare dal webhook.
    registrante_id  bigint NOT NULL REFERENCES sensori_registranti(id) ON DELETE CASCADE,
    segreto_sha256  bytea NOT NULL,
    creata_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT sensori_ttn_applicazione_chk
        CHECK (applicazione ~ '^[a-z0-9](-?[a-z0-9])*$' AND length(applicazione) BETWEEN 2 AND 36),
    CONSTRAINT sensori_ttn_segreto_chk CHECK (length(segreto_sha256) = 32)
);
CREATE INDEX IF NOT EXISTS sensori_ttn_registrante_idx ON sensori_ttn (registrante_id);

-- Una richiesta porta la CSR (MQTT, HTTP firmato) oppure DevEUI e
-- applicazione (LoRaWAN), mai entrambi.
ALTER TABLE sensori_richieste ALTER COLUMN csr DROP NOT NULL;
ALTER TABLE sensori_richieste ADD COLUMN IF NOT EXISTS dev_eui text;
ALTER TABLE sensori_richieste ADD COLUMN IF NOT EXISTS ttn_applicazione text;
ALTER TABLE sensori_richieste DROP CONSTRAINT IF EXISTS sensori_richieste_modo_chk;
-- Ogni confronto del ramo LoRaWAN ha il suo IS NOT NULL: una regex su NULL
-- dà NULL, e un CHECK che vale NULL passa.
ALTER TABLE sensori_richieste ADD CONSTRAINT sensori_richieste_modo_chk CHECK (
    (csr IS NOT NULL AND dev_eui IS NULL AND ttn_applicazione IS NULL)
    OR (csr IS NULL
        AND dev_eui IS NOT NULL AND dev_eui ~ '^[0-9A-F]{16}$'
        AND dev_eui <> '0000000000000000'
        AND ttn_applicazione IS NOT NULL
        AND ttn_applicazione ~ '^[a-z0-9](-?[a-z0-9])*$'
        AND length(ttn_applicazione) BETWEEN 2 AND 36)
);
-- Come per l'id: due richieste aperte con lo stesso DevEUI sono un doppio invio.
CREATE UNIQUE INDEX IF NOT EXISTS sensori_richieste_dev_eui_aperta_uniq
    ON sensori_richieste (dev_eui) WHERE stato = 'in_attesa';

ALTER TABLE sensor_devices ADD COLUMN IF NOT EXISTS dev_eui text;
ALTER TABLE sensor_devices ADD COLUMN IF NOT EXISTS ttn_applicazione text
    REFERENCES sensori_ttn(applicazione) ON DELETE SET NULL;
ALTER TABLE sensor_devices DROP CONSTRAINT IF EXISTS sensor_devices_dev_eui_chk;
ALTER TABLE sensor_devices ADD CONSTRAINT sensor_devices_dev_eui_chk
    CHECK (dev_eui ~ '^[0-9A-F]{16}$' AND dev_eui <> '0000000000000000');
CREATE UNIQUE INDEX IF NOT EXISTS sensor_devices_dev_eui_uniq
    ON sensor_devices (dev_eui) WHERE dev_eui IS NOT NULL;
CREATE INDEX IF NOT EXISTS sensor_devices_ttn_applicazione_idx
    ON sensor_devices (ttn_applicazione);

-- Il webhook gira nell'ingestore, sotto il ruolo ristretto della 079: legge il
-- DevEUI e l'applicazione del dispositivo, e lo SHA-256 del segreto. Non il
-- registrante.
GRANT SELECT (dev_eui, ttn_applicazione) ON public.sensor_devices TO limen_ingestore;
GRANT SELECT (applicazione, segreto_sha256) ON public.sensori_ttn TO limen_ingestore;
