-- 070 — da dove viene la portata ordinaria di un nodo GloFAS.
--
-- La 068 la riempiva solo l'API pubblica di Open-Meteo, a ~52 chiamate per
-- nodo e un tetto di 10.000 al giorno: tre settimane per l'Italia. Ora la può
-- calcolare anche `limen glofas-ewds` dall'Early Warning Data Store di
-- Copernicus, in un solo download. I due numeri sono confrontabili solo se
-- vengono dalla stessa versione del modello GloFAS che Open-Meteo usa per la
-- previsione (la 4 al 2026-10-11): la colonna dice quale, perché il giorno in
-- cui Open-Meteo passa alla 5 i riferimenti `ewds:version_4_0` vanno rifatti.
--
-- Le righe esistenti vengono da Open-Meteo.

ALTER TABLE glofas_riferimento
    ADD COLUMN IF NOT EXISTS fonte text NOT NULL DEFAULT 'open-meteo';
