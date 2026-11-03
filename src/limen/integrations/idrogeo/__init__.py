"""ISPRA IdroGEO.

Il vecchio client del WFS ``geoserver/idrogeo/frane/ows`` non c'è più: dal
2026 risponde 401 a un utente anonimo, e il job settimanale che lo usava
registrava ogni lunedì una versione vuota. IFFI e mosaici arrivano dai
download open data di IdroGEO (pacchetto ``ispra-idrogeo``), caricati nel
PostGIS di GeoServer e letti da ``geoserver_source``.
"""
