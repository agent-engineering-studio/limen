# Deployment

> Three documented targets, **identical code**: dev/test on Neon,
> demo / production on **Aruba VPS + Docker**, enterprise alternative
> on **Azure Container Apps**. Switching environments changes only the
> env vars, never the source.

## Common env vars

| Variable | Notes |
|---|---|
| `DB__CONNECTION_STRING` | PostgreSQL DSN; add `?sslmode=require` for Neon. |
| `DB__POOL_MIN_SIZE` / `DB__POOL_MAX_SIZE` | asyncpg pool. Defaults 2 / 20. |
| `OBJECT_STORE__BACKEND` | `filesystem` (default) or `s3`. |
| `OBJECT_STORE__ROOT` | Filesystem root (`filesystem` only). |
| `OBJECT_STORE__BUCKET` / `__PREFIX` / `__REGION` / `__ENDPOINT_URL` / `__ACCESS_KEY_ID` / `__SECRET_ACCESS_KEY` | S3-compatible (MinIO / Aruba Cloud Object Storage / R2 / B2). |
| `SCHEDULER__CACHE_CLEANUP` | `apscheduler` (works on Neon) or `pg_cron`. |
| `API__HOST` / `API__PORT` | uvicorn bind. Default `0.0.0.0:8080`. |
| `API__CORS_ORIGINS` | JSON array; tighten in prod. |
| `API__PG_TILESERV_URL` | Where the `/api/tiles` proxy redirects. |
| `API__OTEL_OTLP_ENDPOINT` | OTLP/HTTP. Set to the observability container. |
| `LLM__PROVIDER` | Optional override: `anthropic` / `openai` / `foundry` / `ollama`. |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `FOUNDRY_*` / `AZURE_AI_*` / `ANTHROPIC_FOUNDRY_*` | Provider credentials. Resolver precedence: Anthropic → OpenAI → Foundry → Ollama. |
| `LLM__OLLAMA_BASE_URL` | Fallback local LLM, default `http://localhost:11434`. |
| `NOTIFICATIONS__ENABLED_CHANNELS` | JSON array, e.g. `["mqtt","email"]`. |
| `NOTIFICATIONS__TELEGRAM__*` / `__MQTT__*` / `__EMAIL__*` | Per-channel config. |
| `ALERT__MIN_LEVEL` | `Low` / `Moderate` / `High` (default) / `VeryHigh`. |
| `ALERT__DEDUP_WINDOW_MINUTES` | default 180. |
| `ALERT__MAP_BASE_URL` | Where alert deep links point. |

Full `.env.example` is at the repo root.

## Target A — Neon (dev / test)

The fastest "fresh laptop → working stack" path. Neon serverless
Postgres ships PostGIS; pg_cron is unavailable, so APScheduler runs
the periodic jobs.

```bash
export DB__CONNECTION_STRING="postgresql://user:password@ep-xxxx.aws.neon.tech/limen?sslmode=require"
export SCHEDULER__CACHE_CLEANUP=apscheduler

uv sync --all-groups
uv run limen migrate
uv run limen seed
uv run limen bootstrap-static
uv run limen serve
```

Frontend (separate terminal):

```bash
cd frontend
cp .env.local.example .env.local
npm ci
npm run dev
# → http://localhost:5173
```

Notes:

* **Branching**: open a Neon branch per feature; the migration runner
  is idempotent so the same `limen migrate` works on every branch.
* **Scale-to-zero**: Neon hibernates after inactivity; the first request
  after a long pause will take a few extra seconds.

## Target B — Aruba VPS + Docker (demo + prod)

This is the canonical production target. Single VPS, Docker engine,
docker compose (no Kubernetes).

### Demo / single-host

```bash
# On the VPS, as the deploy user:
git clone https://github.com/agent-engineering-studio/limen.git
cd limen
docker compose -f infra/docker/docker-compose.demo.yml up -d --build

# Bring observability up alongside:
docker compose \
  -f infra/docker/docker-compose.demo.yml \
  -f infra/docker/docker-compose.observability.yml \
  up -d --build
```

Services exposed:

| Service | Port | Notes |
|---|---|---|
| Postgres + PostGIS | 5432 | Persistent volume `limen-pgdata`. |
| Limen API | 8080 | `/docs`, `/health`, `/api/*`. |
| pg_tileserv | 7800 | Vector tiles for the matview. |
| Mosquitto | 1883 | Local MQTT broker. |
| Frontend (`--profile frontend`) | 5173 | Vite dev server. |
| Grafana | 3000 | When the observability compose is also up. |
| OTLP gRPC | 4317 | OpenTelemetry collector ingress. |
| OTLP HTTP | 4318 | Same as above. |

### Production hardening

* **DBaaS option**: if a PostGIS-capable managed PostgreSQL is
  available on Aruba Cloud, point `DB__CONNECTION_STRING` at it and
  drop the `postgres` service from the compose.
* **TLS**: front the API with nginx or Caddy doing ACME for
  `api.limen.example`; redirect `:80` → `:443`.
* **Object storage**: switch to S3-compatible (MinIO sidecar or Aruba
  Cloud Object Storage). PostGIS still stores only references.
* **Backups**: see [`runbook.md`](./runbook.md). `pg_basebackup` to an
  external Aruba volume nightly.
* **Secrets**: store provider keys + Clerk secrets in a per-environment
  `.env` mounted read-only into the container; never bake into the
  image.

### Deploy from CI

The [`deploy-aruba.yml`](../.github/workflows/deploy-aruba.yml)
workflow ships the latest `ghcr.io/agent-engineering-studio/limen-api`
image via SSH + `docker compose pull/up`. It is **manual** and gated by
the `aruba-prod` GitHub Environment (required reviewers + secrets).

Required secrets on the `aruba-prod` environment:

| Secret | Value |
|---|---|
| `ARUBA_SSH_HOST` | VPS IP / FQDN |
| `ARUBA_SSH_USER` | Deploy user in the `docker` group |
| `ARUBA_SSH_PRIVATE_KEY` | SSH private key |
| `ARUBA_COMPOSE_PATH` | Absolute path to the compose file on the VPS |

Trigger: GitHub UI → "Actions" → "deploy-aruba" → "Run workflow".

## Target C — Azure Container Apps (enterprise alternative)

When the customer needs Azure compliance / IAM. The same image runs
unchanged; only the build/push surface and the orchestration change.

### One-time setup

```bash
# Resource group + ACR + Container App environment
az group create -n limen-rg -l italynorth
az acr create -n limen -g limen-rg --sku Basic --admin-enabled true
az containerapp env create -n limen-env -g limen-rg -l italynorth

# Postgres (Flex Server) with PostGIS extension
az postgres flexible-server create \
  -n limen-pg -g limen-rg -l italynorth \
  --tier Burstable --sku-name Standard_B1ms --version 16
az postgres flexible-server parameter set \
  -n limen-pg -g limen-rg --name azure.extensions --value POSTGIS

# Initial Container App
az containerapp create \
  -n limen-api -g limen-rg --environment limen-env \
  --image limen.azurecr.io/limen-api:latest \
  --registry-server limen.azurecr.io \
  --target-port 8080 --ingress external \
  --env-vars DB__CONNECTION_STRING=secretref:db-dsn \
             SCHEDULER__CACHE_CLEANUP=apscheduler
```

### Continuous deploy

[`deploy-azure.yml`](../.github/workflows/deploy-azure.yml) builds the
image, pushes it to ACR, and rolls a new Container App revision via
`az containerapp update`. Same manual gate as Aruba (environment
`azure-prod`).

Required secrets on the `azure-prod` environment:

| Secret | Value |
|---|---|
| `AZURE_CREDENTIALS` | `az ad sp create-for-rbac --sdk-auth` JSON |
| `AZURE_RESOURCE_GROUP` | `limen-rg` |
| `AZURE_CONTAINER_APP` | `limen-api` |
| `AZURE_REGISTRY` | `limen.azurecr.io` |
| `AZURE_REGISTRY_USERNAME` / `AZURE_REGISTRY_PASSWORD` | ACR creds |

### Notes

* Container Apps scale to zero — the first request after inactivity
  takes a few seconds (Container App warmup + Neon-like behaviour on
  the Flex Server depending on plan).
* Use Azure Key Vault for the provider keys, referenced as
  `secretref:` in the Container App env.
* Wire OTLP to Azure Monitor / Application Insights via the OTel
  collector — same `API__OTEL_OTLP_ENDPOINT` knob, different sink.

## Provider-agnostic guarantees

These hold across all three targets — they are the design contract:

1. Migrations are idempotent: running `limen migrate` multiple times
   is a no-op when no new files are pending.
2. The scoring engine is pure: identical input ⇒ identical output, no
   matter where it runs.
3. Notification channels are independent: a misconfigured Telegram
   bot never blocks MQTT or Email.
4. `mv_latest_risk` is the single tile source: any DB the API can
   reach can host the matview and pg_tileserv reads it.
5. The frontend SPA never holds environment-specific code — only
   `VITE_API_URL` and `VITE_TILESERV_URL` differ per deployment.
