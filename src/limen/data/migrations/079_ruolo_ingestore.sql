-- 079 — un ruolo per l'ingestore dei sensori di terzi (#267, epic #247).
--
-- L'ingestore v2 (#252) legge messaggi che chiunque abbia un certificato può
-- aver scritto, e finora lo faceva con le credenziali del worker, che può
-- tutto. Con `limen_ingestore` un bug nel parser o nella pipeline non arriva
-- a `risk_assessments`, alle allerte, al livello di fiducia di un dispositivo
-- né al registro dei registranti.
--
-- Può: leggere il registro dei dispositivi e le osservazioni (il controllo di
-- qualità guarda i campioni recenti), scrivere osservazioni, e aggiornare di
-- un dispositivo **solo** sequenza, ultimo dato, stato e `updated_at` (lo
-- stato compreso il togliere una quarantena: lo impedisce il codice, non il
-- ruolo, che con un permesso per colonna non distingue i valori). Non può
-- cambiare `livello`, `cell_id`, `location` né `calibration`, né creare le
-- partizioni: quelle le crea il worker col suo ruolo, all'avvio e ogni mese.
--
-- Nasce senza password: la mette l'API all'avvio da
-- `IOT__CITTADINI__DB_PASSWORD`, come per `limen_tiles` (078). Senza password
-- l'ingestore resta sul pool principale.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'limen_ingestore') THEN
        CREATE ROLE limen_ingestore LOGIN;
    END IF;
END $$;

GRANT USAGE ON SCHEMA public TO limen_ingestore;

-- Da zero su queste due tabelle, anche dove il ruolo esisteva già. Gli
-- attributi e le appartenenze di un ruolo creato a mano non si toccano: un
-- ALTER ROLE NOSUPERUSER fallirebbe su Neon e fermerebbe le migrazioni.
REVOKE ALL ON public.sensor_devices, public.sensor_observations FROM limen_ingestore;

-- Colonna per colonna: `registrante_id` (077) resta fuori, e così ogni
-- colonna che verrà aggiunta finché una migrazione non la concede.
GRANT SELECT (id, device_type, cell_id, location, calibration, status,
              last_seen_at, metadata, livello, ultima_sequenza)
    ON public.sensor_devices TO limen_ingestore;
GRANT UPDATE (ultima_sequenza, last_seen_at, status, updated_at)
    ON public.sensor_devices TO limen_ingestore;

-- Su una tabella partizionata i permessi si controllano sul padre.
GRANT SELECT, INSERT ON public.sensor_observations TO limen_ingestore;
GRANT USAGE ON SEQUENCE public.sensor_observations_id_seq TO limen_ingestore;
