-- 049 — lo storico smette di riscrivere ogni ora le celle che non cambiano (#135).
--
-- IL FATTO. Lo sweep orario scrive una riga per cella e per pericolo:
-- 312.550 celle × 3 pericoli × 24 giri fanno ~19 milioni di righe al giorno
-- (misurate: 18.898.377 nella sola partizione del 2026-09-20). Il
-- 2026-09-28 hanno riempito i 200 GB di `/srv/pgfast` e Postgres è andato in
-- crash loop: non completava il recovery perché il WAL non aveva un byte
-- dove scriversi.
--
-- La maggioranza assoluta di quelle righe dice la stessa cosa dell'ora
-- prima. La distribuzione obiettivo dichiarata in `landslide.yaml` è 70%
-- «Nessuno» e 20% «Basso»: il 90% del volume è fermo per definizione, e
-- riscriverlo ventiquattro volte al giorno non aggiunge una sola
-- informazione.
--
-- Dal #125 lo stato corrente vive in `latest_risk`, che è completa per
-- costruzione. Quindi `risk_assessments` non deve più essere completa: è lo
-- *storico*, e uno storico può permettersi di registrare i cambiamenti
-- invece dei fotogrammi.
--
-- Le due colonne che servono a deciderlo:
--
-- `history_at` — quando è stata scritta l'ultima riga di storico per questa
-- cella, che è una cosa diversa da `computed_at` (l'ultimo calcolo, che
-- avviene ogni ora anche quando non si scrive niente). Serve al battito: una
-- cella immobile deve comunque lasciare una traccia ogni tanto, altrimenti
-- la retention le fa sparire l'ultima riga e la sua storia si azzera.
--
-- `run_id` — quale sweep ha prodotto questo stato. Lo usa
-- `attach_narrative`: prima raggiungeva `latest_risk` unendo tre colonne a
-- `risk_assessments`, e con lo storico rado quell'unione troverebbe solo le
-- celle cambiate — il briefing arriverebbe a una manciata di celle invece
-- che all'area intera.

ALTER TABLE latest_risk ADD COLUMN IF NOT EXISTS history_at timestamptz;
ALTER TABLE latest_risk ADD COLUMN IF NOT EXISTS run_id bigint;

-- Le righe già presenti hanno una riga di storico contemporanea al loro
-- ultimo calcolo: è vero per costruzione, perché fino a questa migrazione
-- ogni calcolo scriveva anche lo storico.
UPDATE latest_risk SET history_at = computed_at WHERE history_at IS NULL;

COMMENT ON COLUMN latest_risk.history_at IS
  'Ultimo istante per cui esiste una riga in risk_assessments per questa cella (#135).';
COMMENT ON COLUMN latest_risk.run_id IS
  'Sweep che ha prodotto questo stato; lo usa attach_narrative per raggiungere tutta l''area.';
