-- Il database del registry MLflow, separato da quello applicativo (#78).
--
-- Il file store è deprecato da MLflow 2.x e il registry dei modelli non ci
-- funziona affatto: senza un backend a database `mlflow models
-- transition-stage` — il cancello di promozione, che resta manuale per
-- invariante — non ha dove scrivere.
--
-- Separato e non uno schema dentro `limen`: MLflow gestisce le proprie
-- migrazioni con Alembic e le applica da solo al primo avvio. Farlo convivere
-- con le migrazioni a checksum di Limen significherebbe due runner sullo
-- stesso search_path.
--
-- Gli script di initdb girano **solo alla prima creazione del cluster**. Su un
-- cluster già avviato o ripristinato lo crea `crea_database_mlflow`, all'avvio
-- dell'API e con `limen migrate` (#327).
SELECT 'CREATE DATABASE mlflow'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'mlflow')\gexec
