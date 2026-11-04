-- 087 — lo schema dei vettori ISPRA e ISTAT caricati senza GeoServer (#426, epic #409).
--
-- `limen carica-vettori` vi carica gli shapefile della cartella di GeoServer
-- con gli stessi nomi di tabella che crea mcp-geo-server (IFFI per regione,
-- mosaici PAI e idraulica, `com01012023_g`): così `geoserver-sync`,
-- `seed-comuni` e il lookup dei comuni leggono da qui con
-- GEOSERVER_SOURCE__SCHEMA_NAME=sorgenti, senza un secondo PostGIS né un
-- GeoServer accesi. Le tabelle le crea il comando, non una migrazione:
-- dipendono da quali shapefile ci sono.
--
-- Nessun GRANT a `limen_tiles`: sono sorgenti, non layer della mappa.

CREATE SCHEMA IF NOT EXISTS sorgenti;
