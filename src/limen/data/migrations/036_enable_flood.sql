-- Abilita il pericolo alluvione — issue #63.
--
-- La riga esisteva dalla migrazione 028 con `enabled = false`: non c'era né
-- motore né configurazione. Ora ci sono entrambi, più i due trigger e lo
-- sweep previsionale a 48 h.
--
-- Nota operativa: la suscettibilità viene dal mosaico idraulico ISPRA in
-- `flood_hazard_subdiv`, popolato da `limen bootstrap-static` con
-- GEOSERVER_SOURCE__DB_DSN configurato. Senza quel layer ogni cella prende il
-- valore di ripiego `susceptibility.unmapped` e la mappa alluvione è uniforme
-- — leggibile, ma non discriminante. È un caricamento dati, non codice.

UPDATE hazards SET enabled = true WHERE hazard = 'flood';
