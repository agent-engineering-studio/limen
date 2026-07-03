# Runbook operativo

Riferimento per gli operatori dello stack V1 in esecuzione. Da usare
insieme a [`deployment.md`](./deployment.md) per il percorso di
installazione e [`architecture.md`](./architecture.md) per la forma del
sistema.

Copertura **nazionale**: 20 regioni italiane. Avvio completo con
`make up` + `make init` (che esegue in sequenza migrate → seed delle 20
regioni → `ingest-events` (truth set e-ITALICA da Zenodo) →
`bootstrap-static` → `calibrate`).

## Ciclo di una giornata normale

| Cosa | Quando | Owner |
|---|---|---|
| Workflow di monitoraggio orario | APScheduler in-process ogni `SCHEDULER__HOURLY_MONITORING_MINUTES` (default 60) | Container API |
| Sync ISPRA IdroGEO | APScheduler cron settimanale (lun 03:15 UTC) | Container API |
| Pulizia cache | APScheduler ogni `SCHEDULER__CACHE_CLEANUP_INTERVAL_SECONDS` (default 300) quando `SCHEDULER__CACHE_CLEANUP=apscheduler` | Container API |
| Refresh `mv_latest_risk` | In coda a ogni chiamata `PersistResultExecutor` | Workflow |

La sorgente dei dati statici ISPRA è il **PostGIS di GeoServer**
(`mcp-geoserver`). Il componente H è attivo a partire dal mosaico di
pericolosità idraulica.

## Sonde di salute

* **Liveness** — `GET /health` restituisce 200 con i booleani `pool` e
  `cache`. L'orchestratore dei container dovrebbe riavviare dopo 5+
  fallimenti consecutivi.
* **Readiness** — `GET /ready` restituisce 503 finché il lifespan non ha
  completato il bootstrap. Da usare come health check del load
  balancer; l'`HEALTHCHECK` di `infra/docker/Dockerfile.api` punta già
  a questo endpoint.

## Comandi operativi comuni

```bash
# Workflow one-shot per un'AOI (usa i canali configurati via env)
LIMEN_MONITOR_AOI=it-puglia uv run limen monitor-once

# Ricalcola s_static + stat di normalizzazione per-AOI, esegue il gate §2.5 S↔ISPRA
uv run limen calibrate

# Ingest del truth set e-ITALICA (eventi da Zenodo) usato dal backtest
uv run limen ingest-events

# Replay di una qualsiasi finestra — scrive reports/backtest_<aoi>_<start>_<end>.md
# (pioggia CERRA + truth set e-ITALICA)
LIMEN_BACKTEST_AOI=it-puglia \
LIMEN_BACKTEST_START=2018-10-28T00:00:00+00:00 \
LIMEN_BACKTEST_END=2018-11-02T00:00:00+00:00 \
  uv run limen backtest

# Innesca un test della pipeline di alert (cella high-level sintetizzata sotto)
docker compose -f infra/docker/docker-compose.demo.yml exec api \
  python -c "import asyncio; from limen.cli.monitor_once import run; asyncio.run(run())"
```

## Backup

PostGIS custodisce la source of truth. L'ObjectStore contiene solo i
byte dei raster referenziati da `raster_refs` — il DB ha i checksum,
quindi un re-pull è verificabile.

### Dump logico (AOI piccola / dev)

```bash
docker compose -f infra/docker/docker-compose.demo.yml exec postgres \
  pg_dump -U limen -d limen --format=custom --no-owner \
          --file=/var/lib/postgresql/data/limen.dump
```

### Base backup fisico (prod, VPS self-hosted)

Configurare `wal_level=replica` e usare `pg_basebackup` verso un volume
esterno. Documentare qui sotto nel runbook la procedura di restore.

### Restore

```bash
docker compose -f infra/docker/docker-compose.demo.yml exec postgres \
  pg_restore -U limen -d limen --clean --if-exists /var/lib/postgresql/data/limen.dump
```

Dopo un restore, **rieseguire il refresh della matview**:

```sql
SELECT refresh_mv_latest_risk();
```

### ObjectStore

* Backend `filesystem`: rsync del volume montato fuori dalla macchina
  via cron.
* Backend `s3`-compatibile: usare le primitive di
  snapshot/replicazione del fornitore (R2, B2, MinIO espongono tutti
  regole di lifecycle).

## Playbook per gli incidenti

### "Tutti i run di monitoraggio sono vuoti"

1. Controllare `GET /ready` e `/health`. Se 503, controllare i log del
   lifespan per fallimenti delle migrazioni.
2. Verificare che la griglia dell'AOI esista: `SELECT COUNT(*) FROM grid_cells WHERE aoi_id = 'it-puglia';`
3. Verificare che `cell_static_factors` abbia righe: stessa query su
   `cell_static_factors`. Se 0, eseguire `uv run limen bootstrap-static`.
4. Controllare la raggiungibilità di Open-Meteo — il
   `MeteoFetchExecutor` degrada silenziosamente a `None` su un 5xx ma
   logga `integration.degraded`.

### "Gli alert non partono"

1. Verificare che almeno una cella superi `ALERT__MIN_LEVEL`. La
   `GET /api/aoi/{id}/risk/latest` (Phase 5) mostra le ultime classi.
2. Controllare `alert_dispatches` per righe recenti di quella cella: se
   una riga rientra nella finestra di dedup, l'executor ha soppresso la
   ripetizione by design. Regolare `ALERT__DEDUP_WINDOW_MINUTES` se
   necessario.
3. Verificare che i canali siano elencati in
   `NOTIFICATIONS__ENABLED_CHANNELS` E che le credenziali di ciascun
   canale siano impostate. Un canale non configurato restituisce
   silenziosamente `False` — nessun errore, nessun alert.
4. Ispezionare i log per `notifications.channel.error` (un canale ha
   sollevato un'eccezione) o `notifications.dispatch.empty` (nessun
   canale configurato).

### "Il sync ISPRA IdroGEO sta fallendo"

1. Il sync settimanale degrada con grazia su 5xx — registra una riga
   `dataset_versions` vuota con hash vuoto e salta le scritture. Il
   workflow resta utilizzabile; si hanno solo IFFI/PAI stantii finché
   ISPRA non torna disponibile.
2. Controllare `SELECT * FROM dataset_versions WHERE source = 'ispra' ORDER BY fetched_at DESC LIMIT 5;`.
3. Retry manuale: `uv run python -m limen.integrations.idrogeo.sync_job` (oppure
   attendere il tick del lunedì successivo).

### "La mappa è vuota"

1. Verificare che pg_tileserv raggiunga la matview:
   `curl http://pg_tileserv:7800/index.json | jq '.[] | .name'`.
2. Verificare che la matview abbia righe:
   `SELECT COUNT(*) FROM mv_latest_risk WHERE aoi_id = 'it-puglia';`.
3. Se 0, eseguire `SELECT refresh_mv_latest_risk();` o innescare un
   ciclo di monitoraggio (il `PersistResultExecutor` fa il refresh in
   uscita).
4. Verificare che `API__PG_TILESERV_URL` sia impostata nell'env del
   container API.

### "Il lifespan di FastAPI non parte"

Il lifespan va in crash su:

* DB irraggiungibile → controllare `DB__CONNECTION_STRING` +
  l'healthcheck del container `postgres`.
* Migrazione errata → checksum mismatch su un file già applicato. **Non
  modificare le migrazioni applicate** — aggiungerne una nuova.
* Fallimento del resolver LLM → impostare `LLM__PROVIDER` esplicitamente
  o rimuovere l'override così che la precedenza ricada su Ollama. In
  prod si usa un host Ollama con modello qwen; il resolver ricade su
  Ollama se manca l'SDK del provider cloud.

## Osservabilità

Avviare lo stack Grafana LGTM accanto alla demo:

```bash
docker compose \
  -f infra/docker/docker-compose.demo.yml \
  -f infra/docker/docker-compose.observability.yml \
  up -d --build
```

Poi puntare l'API su di esso:

```env
API__OTEL_OTLP_ENDPOINT=http://observability:4318
API__OTEL_SERVICE_NAME=limen-api
```

UI Grafana → `http://localhost:3000` (Viewer anonimo). Le dashboard
provisionate:

* **Limen — risk metrics (§3.9)** — i cinque strumenti custom OTel.
* **Limen — system health** — pool DB, tassi di richiesta, run dei job,
  volume di alert, log recenti.

## Versioni + provenienza

* La versione del motore di scoring attivo è in
  `RegionalThresholds.model_version` (default `limen-deterministic-v1`).
  Ogni `risk_assessments.pipeline_version` persistito la referenzia.
* I dataset esterni sono etichettati da
  `dataset_versions(source, dataset, version)`.
* Le licenze open-data e l'attribuzione di Open-Meteo / ISPRA / INGV /
  EFFIS sono documentate nella sezione "Attribution" del README —
  propagarle a qualsiasi rendering pubblico.

## Deploy

VPS self-hosted + Docker. Nessun cloud provider (no AWS/Azure/GCP).
L'object storage per i backup è S3-compatibile (R2, B2, MinIO).
