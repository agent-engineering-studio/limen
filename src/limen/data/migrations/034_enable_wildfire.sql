-- Abilita il pericolo incendio — issue #62.
--
-- La riga esisteva dalla migrazione 028 con `enabled = false`, perché
-- nient'altro che il motore era pronto: metterlo in `mv_latest_risk` prima
-- del workflow avrebbe aggiunto alla mappa un pericolo che nessuno scrive.
-- Ora lo sweep orario lo valuta, gli alert sono etichettati e deduplicati per
-- pericolo, e la SPA sa disegnarlo con la sua palette.
--
-- Nota operativa: i tre codici di umidità sono ricorsivi e partono dai valori
-- standard, quindi le prime settimane il breakdown porta `spinup: true` e i
-- punteggi vanno letti sapendolo. `limen fwi-backfill` ricostruisce la catena
-- dall'archivio ERA5 e va eseguito prima di mettere la mappa davanti a un
-- operatore. Senza, lo sweep la costruisce da solo un giorno alla volta.
--
-- Finché CORINE non popola `landuse_code` e il DEM non popola `slope_deg`, il
-- termine di terreno è costante e la mappa incendio è, di fatto, la mappa
-- FWI. È il prodotto che EFFIS stesso pubblica per l'Europa, quindi è utile
-- così — ma non è ancora il rischio modulato dal territorio.

UPDATE hazards SET enabled = true WHERE hazard = 'wildfire';
