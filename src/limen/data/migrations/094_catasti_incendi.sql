-- 094 — Catasti regionali delle aree percorse dal fuoco (L. 353/2000, #498).
--
-- Un truth set del backtest incendio accanto ai perimetri EFFIS, che censiscono
-- gli incendi grandi: i catasti hanno anche quelli da un ettaro, in
-- interfaccia urbano-bosco. Tabella a sé e non righe di `fire_perimeters`:
-- quella entra nello sweep (la componente post-incendio F della frana, in
-- `fire_check`) e nella densità FRP, e aggiungere poligoni lì sposterebbe il
-- campione V1 senza un backtest. Qui servono solo a misurare.
--
-- Una riga per incendio: i poligoni dello stesso incendio (il catasto
-- dell'Emilia-Romagna ne fa uno per uso del suolo) sono uniti al caricamento.
-- `fire_date` è il giorno d'inizio o di segnalazione dichiarato dall'ente.

CREATE TABLE IF NOT EXISTS catasti_incendi (
    id                  text PRIMARY KEY,                -- '<fonte>:<chiave dell'ente>'
    fonte               text NOT NULL,                   -- es. 'catasto_sardegna'
    fire_date           date NOT NULL,
    area_ha             double precision NOT NULL,       -- dal poligono, in EPSG:3035
    geom                geometry(MultiPolygon, 4326) NOT NULL,
    dataset_version_id  bigint REFERENCES dataset_versions(id) ON DELETE SET NULL,
    attributes          jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS catasti_incendi_geom_gix ON catasti_incendi USING GIST (geom);
CREATE INDEX IF NOT EXISTS catasti_incendi_data_idx ON catasti_incendi (fire_date);
