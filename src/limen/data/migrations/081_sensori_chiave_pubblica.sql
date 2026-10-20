-- La chiave pubblica del dispositivo, per l'ingresso HTTP firmato (#265).
--
-- Un dispositivo che non tiene aperta una sessione MQTT consegna le misure
-- con un POST firmato dalla stessa chiave della sua CSR: P-256 (ECDSA, il
-- secure element ATECC608) o Ed25519. Qui sta la SubjectPublicKeyInfo in
-- DER, scritta da `limen sensore approva` e mai dal dispositivo. NULL =
-- nessun ingresso HTTP: un dispositivo approvato prima di questa migrazione
-- resta solo MQTT finché non si rilancia `limen sensore approva` sulla sua
-- richiesta, che la ricava dalla CSR salvata.

ALTER TABLE public.sensor_devices ADD COLUMN IF NOT EXISTS chiave_pubblica bytea;

-- Il ruolo dell'ingestore legge le colonne una per una (079): senza questa
-- riga la verifica della firma fallirebbe per permesso, non per firma.
GRANT SELECT (chiave_pubblica) ON public.sensor_devices TO limen_ingestore;
