# Threat model — Limen

## What this project does and where untrusted input enters

Limen scores landslide, flood and wildfire risk for every 1 km² cell of Italy
and publishes it on a public map. It is a Python 3.12 service (FastAPI,
asyncpg + PostGIS, APScheduler worker, an MCP server) plus a Vite/React SPA in
`frontend/`. There is **no user authentication by design**: the map and every
read API are public, and any deployment must be treated as anonymously
reachable from the Internet (behind an nginx reverse proxy).

Untrusted input enters through:

- **Public HTTP API** (`src/limen/api/endpoints/`): query and path parameters
  (AOI ids, ISTAT codes, hazard names, bboxes, tile `z/x/y`, time offsets).
  Tiles are served by PostGIS functions (`risk_at`, `forecast_at`, migrations
  in `src/limen/data/migrations/`), some written in PL/pgSQL with `EXECUTE`.
- **`POST /api/contributi`**: free text from anonymous visitors, forwarded by
  e-mail to the maintainers (`src/limen/core/contributi.py`,
  `src/limen/notifications/email.py`). Rate-limited per client IP taken from
  `X-Real-IP`.
- **A2A JSON-RPC** (`POST /a2a`, `src/limen/a2a/`), including
  `tasks/pushNotificationConfig/set`, which stores a caller-supplied URL.
- **MCP server** (`src/limen/mcp/`): read tools are public; `run_monitor`,
  `build_report`, `forecast_history` require `MCP_ADMIN_TOKEN` and must be
  disabled when it is unset.
- **External data feeds** parsed by the worker, which should be treated as
  untrusted even though they are official sources: Open-Meteo JSON, Copernicus
  EWDS NetCDF/GRIB (`integrations/copernicus/`), EGMS ZIP + GeoTIFF archives
  (`integrations/egms/`), EFFIS/ISPRA WFS (`integrations/effis/`,
  `integrations/idrogeo/`), INGV FDSN/ShakeMap XML, DPC radar rasters, FIRMS
  CSV, MQTT sensor messages (`integrations/iot/`).
- **LLM output**: narrative text produced by a model (`agents/chat_agents/`)
  is stored in `spiegazioni_regione` and rendered by the SPA through
  `frontend/src/lib/markdown.ts`. Model output, and anything that reaches the
  prompt from the feeds above, must be treated as attacker-influenced.

## Components that matter most / least

Most important:

- SQL built anywhere outside asyncpg parameters, and dynamic SQL in the
  PL/pgSQL tile functions.
- HTML/Markdown rendering in the SPA (stored XSS from LLM text or API data).
- Header/content injection in the contributions e-mail path; bypass of its
  rate limit.
- SSRF from the A2A push-notification URL or any other caller-controlled URL.
- Archive and raster parsing (path traversal in ZIPs, oversized or malformed
  NetCDF/GeoTIFF).
- Secrets reaching logs, API responses or error messages (API keys, the CLMS
  service key and its tokens, DSNs). `src/limen/core/logging.py` and
  `SecretStr` settings are the controls.
- MCP admin-token checks (fail-closed when unset, constant-time compare).

Less important but in scope: the scheduler jobs, the CLI (`src/limen/cli/`,
operator-only), the scoring engine (pure functions, no I/O).

Out of scope: `notebooks/`, `llm-training/`, `scripts/`, `data/`,
`infra/` compose files for local development, and the `geodata/` ingestion
CLI (operator-run, URLs restricted to `idrogeo.isprambiente.it` by schema).
Wrong risk scores are a correctness issue, not a security one, unless an
attacker can influence them.

## How to exercise it

The image is built by `.oss-scanner/Dockerfile` and includes a local
PostgreSQL 15 + PostGIS cluster:

```sh
pg_ctlcluster 15 main start
uv run pytest tests/unit                 # no network, no DB
uv run pytest tests/integration          # uses LIMEN_TEST_DATABASE_URL; migrations applied by the fixture
cd frontend && npx vitest run
```

To run the API against the local DB:
`DB__CONNECTION_STRING=$LIMEN_TEST_DATABASE_URL uv run limen migrate && DB__CONNECTION_STRING=$LIMEN_TEST_DATABASE_URL SCHEDULER__ENABLED=false uv run limen serve`
(listens on :8080; `/docs` lists every route). External integrations degrade
to empty results without network access; tests mock them with `respx`.
Some integration tests need MQTT or other containers and will not run offline.

## How you rate severity

- **Critical**: unauthenticated RCE; SQL injection reachable from a public
  endpoint or MCP read tool; bypass of `MCP_ADMIN_TOKEN` that triggers a run.
- **High**: stored XSS in the public SPA; SSRF reaching internal services;
  disclosure of a credential (API key, service key, DB password) to an
  anonymous user or into logs; arbitrary file write from archive parsing.
- **Medium**: reflected XSS; e-mail header injection; rate-limit bypass on
  contributions; a single request that exhausts memory or the DB pool
  (one request, not volumetric flooding).
- **Low**: information disclosure without credentials (stack traces, versions).
- Volumetric DoS and missing security headers that the reverse proxy sets are
  out of scope.

## Anything to leave alone

- The absence of authentication on read endpoints and on the map is a design
  decision, not a finding.
- Public read-only data (risk scores, alerts, comuni) being readable is intended.
- Vulnerabilities in unmodified third-party dependencies: report upstream.

Reports: please include the endpoint or function, a minimal reproducer
(curl command or pytest test) and, where possible, a patch that follows the
repository conventions in `CLAUDE.md` (asyncpg parameters, `structlog`,
`mypy --strict`).
