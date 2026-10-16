-- 076 — protocollo v2 dei sensori: sequenza e dati in ritardo (#252, epic #247).
--
-- Ogni messaggio v2 porta un numero di sequenza che cresce sempre, per
-- dispositivo. `sensor_devices.ultima_sequenza` è l'ultimo accettato: un
-- messaggio con sequenza non maggiore è un replay (o un dispositivo che ha
-- perso la memoria) e viene scartato. Sull'osservazione la sequenza resta
-- per vedere i buchi.
--
-- `in_ritardo`: un dispositivo che resta senza rete conserva le letture e le
-- rimanda al ritorno, e sono spesso le ore del temporale. Non si rifiutano:
-- si salvano marcate, e il rollup orario — l'unica strada verso lo scoring —
-- le esclude. Restano per l'archivio, le Verifiche e il confronto con il
-- radar (#250). Il default false lascia com'è ogni riga V1.5.

ALTER TABLE sensor_devices
    ADD COLUMN IF NOT EXISTS ultima_sequenza bigint;

ALTER TABLE sensor_observations
    ADD COLUMN IF NOT EXISTS sequenza bigint,
    ADD COLUMN IF NOT EXISTS in_ritardo boolean NOT NULL DEFAULT false;
