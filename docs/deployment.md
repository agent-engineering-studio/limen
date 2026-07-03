# Deployment

> Due target documentati, **codice identico**: dev/test su Neon,
> demo / produzione su **VPS self-hosted + Docker**. Cambiare
> ambiente modifica solo le variabili d'ambiente, mai il sorgente.
> Nessun cloud provider è supportato (no AWS/Azure/GCP).

## Variabili d'ambiente comuni

| Variabile | Note |
|---|---|
| `DB__CONNECTION_STRING` | DSN PostgreSQL; aggiungi `?sslmode=require` per Neon. |
| `DB__POOL_MIN_SIZE` / `DB__POOL_MAX_SIZE` | Pool asyncpg. Default 2 / 20. |
| `OBJECT_STORE__BACKEND` | `filesystem` (default) oppure `s3`. |
| `OBJECT_STORE__ROOT` | Root del filesystem (solo `filesystem`). |
| `OBJECT_STORE__BUCKET` / `__PREFIX` / `__REGION` / `__ENDPOINT_URL` / `__ACCESS_KEY_ID` / `__SECRET_ACCESS_KEY` | S3-compatibile (MinIO / R2 / B2). |
| `SCHEDULER__CACHE_CLEANUP` | `apscheduler` (funziona su Neon) oppure `pg_cron`. |
| `API__HOST` / `API__PORT` | Bind uvicorn. Default `0.0.0.0:8080`. |
| `API__CORS_ORIGINS` | Array JSON; restringi in produzione. |
| `API__PG_TILESERV_URL` | Destinazione del proxy `/api/tiles`. |
| `API__OTEL_OTLP_ENDPOINT` | OTLP/HTTP. Punta al container di observability. |
| `LLM__PROVIDER` | Override opzionale: `anthropic` / `openai` / `foundry` / `ollama`. |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `FOUNDRY_*` / `AZURE_AI_*` / `ANTHROPIC_FOUNDRY_*` | Credenziali provider. Precedenza del resolver: Anthropic → OpenAI → Foundry → Ollama. |
| `LLM__OLLAMA_BASE_URL` | LLM locale di fallback, default `http://localhost:11434`. |
| `NOTIFICATIONS__ENABLED_CHANNELS` | Array JSON, es. `["mqtt","email"]`. |
| `NOTIFICATIONS__TELEGRAM__*` / `__MQTT__*` / `__EMAIL__*` | Configurazione per canale. |
| `ALERT__MIN_LEVEL` | `Low` / `Moderate` / `High` (default) / `VeryHigh`. |
| `ALERT__DEDUP_WINDOW_MINUTES` | default 180. |
| `ALERT__MAP_BASE_URL` | Destinazione dei deep link degli alert. |

Il file `.env.example` completo si trova nella root del repository.

## Target A — Neon (dev / test)

Il percorso più rapido "laptop pulito → stack funzionante". Neon
serverless Postgres include PostGIS; pg_cron non è disponibile, quindi
APScheduler esegue i job periodici. **Neon è consentito solo per
dev/test**, mai in produzione.

```bash
export DB__CONNECTION_STRING="postgresql://user:password@ep-xxxx.aws.neon.tech/limen?sslmode=require"
export SCHEDULER__CACHE_CLEANUP=apscheduler

uv sync --all-groups
uv run limen migrate
uv run limen seed
uv run limen bootstrap-static
uv run limen serve
```

Frontend (terminale separato):

```bash
cd frontend
cp .env.local.example .env.local
npm ci
npm run dev
# → http://localhost:5173
```

Note:

* **Branching**: apri un branch Neon per ogni feature; il runner delle
  migrazioni è idempotente, quindi lo stesso `limen migrate` funziona su
  ogni branch.
* **Scale-to-zero**: Neon va in ibernazione dopo un periodo di
  inattività; la prima richiesta dopo una lunga pausa richiederà qualche
  secondo in più.

## Target B — VPS self-hosted + Docker (demo + prod)

È il target di produzione canonico. Singola VPS, Docker engine,
docker compose (niente Kubernetes). Nessun cloud provider.

### Demo / host singolo

```bash
# Sulla VPS, come utente di deploy:
git clone https://github.com/agent-engineering-studio/limen.git
cd limen
docker compose -f infra/docker/docker-compose.demo.yml up -d --build

# Con il profilo geoserver (GeoServer PostGIS come sorgente dati statici ISPRA):
docker compose -f infra/docker/docker-compose.demo.yml --profile geoserver up -d --build

# Con l'observability affiancata:
docker compose \
  -f infra/docker/docker-compose.demo.yml \
  -f infra/docker/docker-compose.observability.yml \
  up -d --build
```

Servizi esposti:

| Servizio | Porta | Note |
|---|---|---|
| Postgres + PostGIS | 5432 | Volume persistente `limen-pgdata`. |
| Limen API | 8080 | `/docs`, `/health`, `/api/*`. |
| pg_tileserv | 7800 | Vector tiles per la matview. |
| Mosquitto | 1883 | Broker MQTT locale. |
| Frontend (`--profile frontend`) | 5173 | Vite dev server. |
| Grafana | 3000 | Quando è attivo anche il compose di observability. |
| OTLP gRPC | 4317 | Ingress del collector OpenTelemetry. |
| OTLP HTTP | 4318 | Come sopra. |

### Hardening di produzione

* **DBaaS**: se è disponibile un PostgreSQL gestito con PostGIS, punta
  `DB__CONNECTION_STRING` verso di esso e rimuovi il servizio `postgres`
  dal compose.
* **TLS**: metti davanti all'API nginx o Caddy con ACME per
  `api.limen.example`; redirect `:80` → `:443`.
* **Object storage**: passa a S3-compatibile (sidecar MinIO / R2 / B2).
  PostGIS continua a memorizzare solo i riferimenti.
* **Backup**: vedi [`runbook.md`](./runbook.md). `pg_basebackup` notturno
  verso un volume esterno.
* **Segreti**: conserva le chiavi provider + i secret Clerk in un file
  `.env` per-ambiente, montato in sola lettura nel container; non
  includerli mai nell'immagine.

### Deploy da CI

Il deploy verso la VPS self-hosted avviene via SSH + `docker compose
pull/up`: pubblica l'ultima immagine
`ghcr.io/agent-engineering-studio/limen-api` sulla VPS. È **manuale** e
protetto da un GitHub Environment (reviewer richiesti + secret).

Il workflow è attualmente
[`deploy-aruba.yml`](../.github/workflows/deploy-aruba.yml) (rinomina
pendente). I secret richiesti sull'ambiente GitHub sono:

| Secret | Valore |
|---|---|
| `ARUBA_SSH_HOST` | IP / FQDN della VPS |
| `ARUBA_SSH_USER` | Utente di deploy nel gruppo `docker` |
| `ARUBA_SSH_PRIVATE_KEY` | Chiave SSH privata |
| `ARUBA_COMPOSE_PATH` | Path assoluto del file compose sulla VPS |

Trigger: GitHub UI → "Actions" → seleziona il workflow → "Run workflow".

## LLM in produzione

Su VPS self-hosted il provider LLM preferito è **Ollama** in esecuzione
sull'host (modello `qwen`); i provider cloud restano solo come fallback.
Imposta `LLM__OLLAMA_BASE_URL` verso l'host Ollama e, se necessario,
`LLM__PROVIDER=ollama` per forzare la scelta.

## Garanzie provider-agnostiche

Valgono su tutti i target — sono il contratto di design:

1. Le migrazioni sono idempotenti: eseguire `limen migrate` più volte è
   un no-op quando non ci sono nuovi file in sospeso.
2. Lo scoring engine è puro: input identico ⇒ output identico, ovunque
   venga eseguito.
3. I canali di notifica sono indipendenti: un bot Telegram mal
   configurato non blocca mai MQTT o Email.
4. `mv_latest_risk` è l'unica sorgente delle tile: qualsiasi DB
   raggiungibile dall'API può ospitare la matview e pg_tileserv la legge.
5. La SPA frontend non contiene mai codice specifico dell'ambiente —
   variano solo `VITE_API_URL` e `VITE_TILESERV_URL` per deployment.
