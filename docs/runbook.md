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

### "Alluvione e incendio danno zero su ogni cella"

Zero esatto ovunque, con `computed_at` recente, non è un territorio calmo:
è l'assenza di dato che arriva fino in fondo. Il breakdown lo dice —
`fire_weather: null` con `spinup: true`, `rain_mm: null`,
`discharge_ratio: null` — e i motori degradano come devono.

1. Contare i degradi dell'ultima giornata:
   `docker logs limen-worker --since 24h | grep -c integration.degraded`.
   Un numero a tre cifre tutto su etichette `openmeteo.*` è il tetto
   giornaliero dell'API pubblica, non un guasto di rete.
2. Confermarlo con una chiamata a mano: la risposta è
   `{"error":true,"reason":"Daily API request limit exceeded..."}`, non un
   timeout.
3. Guardare i nodi FWI: `SELECT day, count(*) FROM fwi_state GROUP BY day
   ORDER BY day DESC LIMIT 8;`. Se il conteggio cala di giorno in giorno,
   la catena si sta spegnendo dal nord — è il fronte del quota che si
   ritira, non una perdita di stato.
4. La cura è l'istanza propria: `make meteo-up`, `make meteo-check`, e
   `OPENMETEO__FORECAST_URL` / `__ARCHIVE_URL` nel `.env` (#142). Portata
   e onde restano sull'API pubblica in ogni caso: GloFAS non è pubblicato
   sul bucket AWS di Open-Meteo.

### "pg_tileserv risponde 404 su una vista appena creata"

Il catalogo di pg_tileserv si legge all'avvio. Una migrazione che crea una
vista o una funzione di tile non la rende visibile finché il container non
riparte: `docker compose -p limen restart pg_tileserv`. Un 404 su una
vista che esiste in Postgres è quasi sempre questo, non un errore di nome.

L'altra causa è il ruolo. pg_tileserv si collega come `limen_tiles`
(migrazione 078, #269), che legge solo i layer della mappa: una vista nuova
va concessa in una migrazione (`GRANT SELECT ON … TO limen_tiles`, o
`SECURITY DEFINER` per una funzione) e aggiunta a `PUBBLICATI` in
`tests/integration/test_ruolo_tiles.py`. Una migrazione che ridefinisce
`risk_at`, `multi_hazard_at` o `forecast_at` ripete `SECURITY DEFINER SET
search_path = public, pg_temp` (`CREATE OR REPLACE` la riporta INVOKER), e una
che ricrea una vista concessa ripete il `GRANT`. Mai collegarlo di nuovo come
`limen`: pubblicherebbe ogni tabella con una geometria, `sensor_devices`
compresa.

### "pg_tileserv non parte" / la mappa è vuota dopo un aggiornamento

La password di `limen_tiles` sta nel `.env` come `DB__TILES_PASSWORD`
(esadecimale, `openssl rand -hex 24`: finisce dentro un URL) e la imposta
l'API all'avvio, così come `uv run limen migrate`. Senza, l'API scrive
`migrate.ruolo_senza_password` (con `ruolo=limen_tiles`) e pg_tileserv riparte in loop perché non
entra. Dopo averla messa: `make up`, poi
`curl -s http://127.0.0.1:7800/index.json | jq 'keys'` deve elencare dodici
layer e nessuna tabella grezza.

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

## Backup e ripristino del training ML

Il dataset di training (37k+ campioni con pioggia CERRA, ~13 h di replay) e
il modello addestrato (registro MLflow) sono artefatti costosi che NON stanno
in git. Prima di migrare macchina o dopo un retrain riuscito:

```bash
make dump-training      # crea data/backups/{training_samples,mlflow}_YYYY-MM-DD.*
```

Sulla macchina nuova (dopo `make init`):

```bash
make restore-training DUMP=data/backups/training_samples_YYYY-MM-DD.dump \
                      MLTGZ=data/backups/mlflow_YYYY-MM-DD.tgz
```

La cartella `data/backups/` è gitignored: va trasportata a parte (chiavetta,
MinIO, asset privato). La produzione NON dipende dal training: il champion
deterministico gira completo con il solo `make init`.

## Broker MQTT dei sensori (#260)

Un Mosquitto dedicato (`limen-mosquitto-sensori`, profilo compose `sensori`),
separato da `limen-mosquitto` delle allerte. Accetta solo dispositivi con un
certificato firmato dalla CA dei sensori, che vive in `$LIMEN_SENSORI_DIR`,
fuori dal repo.

```bash
make sensori-ca-init    # CA, server, ingestore, healthcheck, ACL (idempotente)
make sensori-up         # avvia, sul loopback 127.0.0.1:18883
make sensori-check      # anonimo, CA estranea, ACL, revoca: deve dire «tutti i controlli passati»
```

Per l'esposizione: `infra/nginx/mqtt-sensori.stream.conf` (passthrough TCP
sulla 8883, da installare come root), `ufw allow 8883/tcp` e, con l'IP
dinamico della fibra, l'inoltro della 8883 sul router.

Operazioni ricorrenti:

- **Ogni mese: `make sensori-crl`.** La CRL vale 90 giorni, e una CRL
  scaduta fa rifiutare a Mosquitto *tutti* i dispositivi, non solo i
  revocati. `make sensori-check` avvisa sotto i 30 giorni. Va in un cron.
- **Revocare un dispositivo**: `./scripts/sensori_ca.sh revoca <id>`. Rigenera
  la CRL e manda un SIGHUP al broker, che la rilegge senza staccare gli
  altri. Una sessione **già aperta** del revocato resta in piedi fino alla
  sua prossima riconnessione: se serve buttarlo fuori subito,
  `docker restart limen-mosquitto-sensori` (i dispositivi buoni si
  riconnettono da soli).
- **Firmare un dispositivo**: `./scripts/sensori_ca.sh firma <csr> [giorni]`
  (default 730). Il CN della CSR è l'id del dispositivo: minuscole, cifre e
  trattini; `limen-ingestore` e `limen-salute` sono riservati. Un id che ha già
  un certificato valido si rifiuta (due dispositivi parlerebbero come uno);
  per un rinnovo voluto, `SENSORI_RINNOVO=1 ./scripts/sensori_ca.sh firma …`.
- **Cambiata l'ACL** in `infra/mosquitto-sensori/acl`: `make sensori-ca-init`
  la ricopia con permessi 0600, poi `docker kill -s HUP limen-mosquitto-sensori`.
- **Scadenze**: `./scripts/sensori_ca.sh stato`. Server e ingestore valgono
  825 giorni e l'init li rinnova sotto i 30; la CA vale 10 anni.
- **Backup**: `$LIMEN_SENSORI_DIR/ca` è insostituibile. Persa la chiave della
  CA, ogni dispositivo va riprovisionato a mano. Va nel backup cifrato,
  mai nel repo. **Rifallo dopo ogni firma o revoca**, `make sensori-check`
  compreso (firma dispositivi di prova): una copia vecchia non sa quali
  seriali sono già stati emessi.
- **Dopo un riavvio del server** controlla `docker ps --filter name=sensori`:
  `unless-stopped` non riavvia un container fermato a mano, e il 15 ottobre
  2026 il broker è rimasto giù una notte così. `make sensori-up` lo riporta su.

### Ingestore v2 (#252)

Il worker legge il broker dei sensori con il certificato `limen-ingestore` e
salva le misure dei dispositivi registrati in `sensor_devices`. Per
accenderlo:

1. `make sensori-ca-init` (rende la chiave dell'ingestore leggibile al gruppo,
   0640: il worker gira come `limen` e la legge tramite `group_add`);
2. `IOT__CITTADINI__ENABLED=true` nel `.env`;
3. `make up`: con `LIMEN_SENSORI_DIR` impostato, `docker-compose.sensori-worker.yml`
   monta `$LIMEN_SENSORI_DIR/client` nel worker in `/run/limen-sensori`;
4. nei log del worker, `iot.v2.connesso`.

Spento (`IOT__CITTADINI__ENABLED=false`) nessun messaggio v2 entra: è il
kill switch dei dispositivi di terzi. Ogni scarto è un `iot.v2.scartato` con
l'`esito` (`frequenza`, `quarantena`, `sconosciuto`, `malformato`, `futuro`,
`troppo_vecchio`, `sequenza`, `troppo_grande`, `topic`, `errore`). Un dispositivo messo in quarantena per
frequenza ci resta finché non lo si rimette `online` a mano
(`UPDATE sensor_devices SET status = 'online' WHERE id = …`): il suo LWT non
basta, per scelta.

Un dispositivo che ha perso il contatore di sequenza (flash cancellata,
firmware riscritto) viene scartato con `esito=sequenza` a ogni messaggio,
perché ricomincia da numeri già visti. Dopo aver controllato che sia davvero
lui e non un replay: `UPDATE sensor_devices SET ultima_sequenza = NULL WHERE
id = …`, e il primo messaggio successivo riparte da lì.

### L'ingestore dei sensori con un ruolo suo (#267)

L'ingestore v2 legge messaggi che chiunque abbia un certificato può aver
scritto. Con `IOT__CITTADINI__DB_PASSWORD` nel `.env` (esadecimale, `openssl
rand -hex 24`) scrive come `limen_ingestore` (migrazione 079): osservazioni,
sequenza, ultimo dato e stato, e niente altro — non il livello di un
dispositivo, non i punteggi, non il registro dei registranti. La password la
imposta l'API all'avvio; finché il ruolo non entra, l'ingestore scrive
`iot.v2.ruolo_non_disponibile` e aspetta, senza ripiegare sul ruolo del
worker, mentre il broker tiene i messaggi. Senza la variabile resta sul pool
principale, com'era. Le partizioni le crea comunque il worker col suo ruolo.

### Registrazione dei sensori (#253)

Il modulo in fondo a `#/sensori` è chiuso finché non si mette
`IOT__CITTADINI__REGISTRAZIONE__APERTA=true` nel `.env` (e `make up`).
Prima di aprirlo, controllare che `/tiles/index.json` non elenchi
`sensor_devices` (#269: pg_tileserv come `limen_tiles`, vedi sopra): finché
lo elenca, la posizione esatta di un sensore approvato è pubblica. Una
richiesta non crea un dispositivo: scrive una riga in `sensori_richieste` e
manda una mail a `CONTRIBUTI__DESTINATARI`, con la foto in allegato e i comandi
per decidere. Se la mail non parte, la richiesta non resta.

Si decide **dall'host, dalla radice del repo**: firmare passa da
`scripts/sensori_ca.sh`, e la chiave della CA non entra in nessun container.

```sh
uv run limen sensore richieste                     # le richieste in attesa
uv run limen sensore approva 42                    # firma, crea al livello 0, manda il cert
uv run limen sensore respingi 42
uv run limen sensore revoca pluvio-matera-01       # CRL + quarantena
uv run limen sensore quarantena pluvio-matera-01
uv run limen sensore quarantena --registrante maker@example.org
uv run limen sensore cancella-registrante maker@example.org   # GDPR
```

- `approva` su una richiesta già approvata **rimanda** la mail con lo stesso
  certificato: è il rimedio se la mail non era partita (`sensore.mail_non_partita`).
  Il certificato si salva appena firmato, quindi anche un `approva` fallito a
  metà, rilanciato, non ne firma un secondo. Un dispositivo in quarantena non
  riceve più niente.
- Dopo ogni `approva` o `revoca` la CA è cambiata: rifare il backup
  (`cp -a $LIMEN_SENSORI_DIR/ca /srv/backup/limen-sensori/`).
- `cancella-registrante` revoca e mette in quarantena i dispositivi, poi
  cancella la mail e le richieste: i dispositivi restano senza registrante,
  le misure restano.
- La quota (`MAX_DISPOSITIVI_PER_REGISTRANTE`) conta anche i dispositivi
  revocati e le richieste in attesa.
