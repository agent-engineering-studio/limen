# Limen — Claude Code project guide

> AI multi-factor landslide-risk monitoring for the Italian territory.
> Pilot: **Puglia + Basilicata**. Current state: **Phase 0 + Phase 1 +
> Phase 2 + Phase 3 + Phase 4 + Phase 5** (scaffold + data layer + external
> integrations + static bootstrap + deterministic scoring engine V1
> + MAF agents & workflow + FastAPI host with APScheduler + OTel).
> See `README.md` for full context.

---

## Deployment context (mandatory)

- **Target**: VPS Aruba + Docker containers. **No cloud providers** — no
  AWS, no Azure, no GCP. Stored in memory as `deploy-target`.
- **Database**: PostgreSQL 16 + PostGIS, containerised in production.
  **Neon** is allowed only for dev/test branches.
- **Object storage**: `filesystem` (volume mount) or `s3`-compatible
  (MinIO sidecar, Aruba Cloud Object Storage, R2, B2 — via
  `OBJECT_STORE__ENDPOINT_URL`). Never AWS SDK calls. Never Azure Blob.

---

## Locked invariants (never violate)

| Topic | Rule |
|-------|------|
| Language | Python 3.12+, `uv` for everything (`uv sync`, `uv run`). |
| Layout | `src/limen/...`, package = `limen`. Tests in `tests/`. |
| License | Apache-2.0. |
| DB access | `asyncpg` + the PostGIS hex-EWKB codec in `limen.data.db`. **No ORM.** |
| Migrations | Plain SQL in `src/limen/data/migrations/NNN_*.sql`, applied by `limen.data.migrate`. Tracked with SHA-256 checksums. **NEVER edit an applied migration** — add a new file. Comments count: even a comment-only change breaks the checksum. |
| Object store | Use the `ObjectStore` Protocol only. Never `import boto3` in app code. The factory in `limen.data.object_store.factory` is the only place that picks a backend. |
| Settings | `pydantic-settings` with `env_nested_delimiter="__"`. New env vars go through `limen.config.settings.Settings`. |
| LLM | Resolver order: Anthropic → OpenAI → Foundry → Ollama. Cloud key wins over Ollama unless `LLM__PROVIDER` overrides. On Aruba prod prefer **Ollama**; cloud is fallback. |
| Scheduling | `pg_cron` is optional. The same job must work via APScheduler when pg_cron is absent (Neon). |
| Logging | `structlog.get_logger(__name__)` via `limen.core.logging.get_logger`. **Never `print`.** |
| Geometry CRS | All geometries stored in EPSG:4326. Compute distances/areas in EPSG:3035 (LAEA Europe). |
| Quality gates | `ruff check` + `ruff format` clean, `mypy --strict` clean, `pytest` green before commit. |
| External HTTP | All outbound calls go through `limen.integrations._http` (shared `httpx.AsyncClient` + tenacity policy: 4 attempts, exp backoff cap 60 s, retries on transport errors + 5xx/429). |
| Degradation | Read-only operations that miss external sources return a *neutral result* (`None`, `[]`, `{}`) and log `integration.degraded` — they MUST NOT raise. Writes do raise. |
| Idempotency (sync jobs) | Compute SHA-256 over canonical-JSON of the fetched payloads, look up `dataset_versions(source, dataset, version)`. If the version exists, **skip all writes**. |
| Scoring engine purity | `MultiFactorScoringEngine.score(bundle) -> RiskScore` is a *pure* function: no DB, no network, no LLM. Assembling the bundle is a separate concern. |
| Magic numbers | All weights, thresholds, sigmoid/decay params, and class cutoffs live in `src/limen/config/regional_thresholds.yaml`. Validated by `RegionalThresholds` Pydantic schema at load. There are **no hard-coded constants** in scoring code — tests prove it via YAML override. |
| LLM precedence | `LLM__PROVIDER` override > `ANTHROPIC_API_KEY` > `OPENAI_API_KEY` > Foundry creds > Ollama. Resolver: `limen.agents.llm_factory.resolve_llm_factory`. A cloud key always wins over Ollama unless explicitly overridden. |
| LLM is non-authoritative | ChatAgents (RiskAnalyst, Briefing) only *reformulate* the deterministic scoring engine's numeric output. **Never** alter `score` / `breakdown`. An invariance test (`test_llm_does_not_change_numeric_breakdown`) enforces this. |
| Agents prompts in `*.it.md` | Prompt files live next to the agent in `src/limen/agents/chat_agents/prompts/`. Loaded with `importlib.resources`. Never inline a long prompt in Python source. |
| API has no business logic | Endpoints under `src/limen/api/endpoints/` only call the Phase-4 workflow or the Phase-1 repos. New behaviour goes in `agents/` or `core/`, never in route handlers. |
| DI not globals | Everything routes need is in `AppDependencies` injected via FastAPI `Depends()`. No `from limen.x import _GLOBAL_THING` inside endpoints. |
| APScheduler not pg_cron | Periodic jobs (hourly monitoring, weekly ISPRA sync, cache cleanup when configured) run in-process via APScheduler so the same code works on Neon. |

---

## Code rules

- **Edit existing files** rather than creating new ones unless a new module is
  genuinely needed.
- **No documentation files** (`*.md`) without an explicit user request.
- **No comments** unless the *why* is non-obvious (hidden constraint, subtle
  invariant, workaround). Don't narrate what the code does.
- **No future-proofing**: don't add validation/fallbacks for cases that can't
  happen, don't introduce abstractions for hypothetical second uses.
- **Optional dependencies**: anything in the `storage` dependency group must
  be guarded by a local import inside the function/`__init__`, so the module
  can be imported without the dep installed.
- **Trust internal code**: validate only at boundaries (user input, external
  APIs).
- **Idempotency**: every CLI command (`limen migrate`, `limen seed`, future
  ingest jobs) must be safely re-runnable.
- **Geometries on the wire** are Shapely objects, not WKT strings. The
  PostGIS codec is registered globally.

### Never

- Edit an applied SQL migration file.
- Import a cloud SDK (`boto3`, `azure.*`, `google.*`) outside
  `data/object_store/`.
- Add `from supabase import …` or any BaaS SDK.
- Use `print`, `logging.basicConfig` outside `core/logging.py`, or build a
  bespoke logger.
- Skip `mypy --strict` errors with `# type: ignore` unless paired with a
  one-line *why* and an issue reference.
- Skip pre-commit hooks (`--no-verify`).

---

## Skills to reach for

When the task matches, invoke these skills (via Skill tool / slash command)
before reaching for raw bash:

| Skill | When |
|-------|------|
| `verify` | After a change that affects behaviour (CLI, repo, migration). Confirms it works against a real Postgres+PostGIS, not just unit tests. |
| `code-review` | Before pushing any non-trivial diff. Use `--fix` to apply findings. |
| `simplify` | Quick post-edit cleanup pass (same engine as `code-review --fix`). |
| `run` | When you need to actually run `limen seed` / `limen migrate` to see output. |
| `claude-api` | When (later phases) we add Anthropic SDK calls for the MAF scorer/explainer. Apps built with this skill include prompt caching by default. |
| `loop` | For poll-style monitoring of long-running ingestion jobs (Phase 2+). |
| `update-config` | Permissions / hooks / env vars in `settings.json`. |
| `fewer-permission-prompts` | If we keep seeing the same approval prompt, add it to project `settings.json`. |
| `init` | Don't re-run — this file is the result. |

**Skills NOT relevant to this project:**

- All `clerk-*` skills — Limen doesn't use Clerk for auth.
- `statusline-setup`, `keybindings-help` — user-environment, not project.

---

## Common commands

```bash
make install                # uv sync --all-groups
make up-dev                 # docker compose: Postgres 16 + PostGIS 3.5 + pg_cron + pgvector
make seed                   # apply migrations + load Puglia/Basilicata AOIs + 1 km grid
make migrate                # apply pending SQL migrations only
uv run limen bootstrap-static   # one-shot fill of cell_static_factors (IFFI density + PAI)
uv run limen calibrate          # precompute s_static + per-AOI norm stats; S vs ISPRA gate
uv run limen backtest           # replay historical window; §2.5 hit rate / FAR / lead time
                                # (env knobs: LIMEN_BACKTEST_AOI / START / END / HIGH_LEVEL)
uv run limen monitor-once       # run the MAF workflow once for an AOI
                                # (env knobs: LIMEN_MONITOR_AOI / CELL_LIMIT)
uv run limen serve              # start the FastAPI server on API__HOST:API__PORT (default :8080)
                                # /docs , /redoc , /health , /ready , /api/...
make test                   # unit + integration (testcontainers)
make test-unit              # fast, no Docker
make lint                   # ruff check
make format                 # ruff format
make typecheck              # mypy --strict on src/
make check                  # lint + typecheck + test
```

**Apple Silicon note**: integration tests auto-pick
`imresamu/postgis-arm64:16-3.5` (the official `postgis/postgis` image has
no arm64 manifest). Override with `LIMEN_TEST_POSTGIS_IMAGE`.

---

## Repository map

```
src/limen/
├── cli/                 # `limen` entry point + subcommands (migrate, seed, bootstrap-static)
├── config/              # pydantic-settings (DB, OBJECT_STORE, LLM, SCHEDULER)
├── agents/
│   ├── llm_factory/     # ChatClient Protocol + Anthropic/OpenAI/Foundry/Ollama + Stub + resolver
│   ├── workflow_runtime/# MAF-shaped shim: Executor, @handler, WorkflowBuilder
│   ├── executors/       # area_resolver, static_factors, meteo_fetch, seismic_check,
│   │                    # fire_check, sensor_fetch (stub), risk_scoring, escalation_gate,
│   │                    # persist_result, alert_dispatch (logging stub)
│   ├── chat_agents/     # RiskAnalyst + Briefing (+ Italian prompts in *.it.md)
│   └── workflows/       # build_landslide_workflow + escalation_workflow placeholder
├── api/
│   ├── main.py          # FastAPI app factory + lifespan
│   ├── dependencies.py  # AppDependencies + typed Depends() providers
│   ├── schemas.py       # Pydantic request/response DTOs
│   ├── endpoints/       # health/ready, aoi, monitor, risk, alerts, tiles
│   └── jobs/            # APScheduler: hourly_monitoring, weekly_idrogeo_sync,
│                        # cache_cleanup, registration
├── observability/       # OTel tracing setup + custom metric instruments
├── core/
│   ├── abstractions/    # external-source Protocols (OpenMeteo, IdroGeo, Ingv, Effis)
│   ├── features/        # CellFeatureBundle assembler (single V1+V2 path)
│   ├── models/          # risk DTOs + MonitoringContext + Assessment
│   ├── scoring/         # deterministic V1 engine + Caine / API / seismic / post-fire
│   ├── logging.py
│   ├── scheduling.py    # APScheduler (Neon path)
│   └── llm_resolver.py
├── integrations/
│   ├── _http.py             # shared httpx client + tenacity policy + degrade_gracefully
│   ├── openmeteo/           # forecast + ERA5 archive + CachedOpenMeteoClient wrapper
│   ├── idrogeo/             # ISPRA WFS client + parsers + idempotent sync_job
│   ├── ingv/                # FDSN events + ShakeMap grid + sync_job
│   ├── effis/               # Copernicus EFFIS fire perimeters + sync_job
│   └── static_bootstrap/    # cell_static_factors orchestrator (PostGIS-only)
└── data/
    ├── db.py            # asyncpg pool + PostGIS codec
    ├── migrate.py       # idempotent SQL migrations runner
    ├── migrations/      # NNN_*.sql, immutable once applied
    ├── object_store/    # ObjectStore Protocol + filesystem | s3
    ├── caching/         # PostgresCache + CachedOpenMeteoClient
    ├── repos/           # aoi, grid, iffi, pai, susceptibility, seismic, fire,
    │                    # raster_refs, dataset_versions, cell_static_factors
    └── seed/            # Puglia + Basilicata placeholder GeoJSON + loader

infra/postgres/          # Dockerfile.db + pg_cron config + initdb SQL
infra/docker/            # docker-compose.dev.yml
tests/{unit,integration}
```

---

## Phase boundary (what's out of scope NOW)

Do not start implementing — these land in later prompts and have explicit
extension points already:

- Frontend (map-first SPA with pg_tileserv) — Phase 6.
- Notifications, IoT ingestion, ML/MLOps — Phase 7+.
- V2 ML engine — drop-in replacement of `MultiFactorScoringEngine` that
  consumes the same `CellFeatureBundle`.
- DEM derivatives (TINITALY → slope/aspect/curvature/TWI), CORINE, ISPRA Carta Geologica
  vettoriale: `cell_static_factors` columns stay NULL until the raster/vector ingest
  pipeline lands. The bootstrap pipeline already logs `static_bootstrap.skip` for each.

If asked to "make it work end-to-end", clarify which phase the user wants
to advance.

---

## Where to look

- **README.md** — public-facing overview, architecture diagram, schema
  highlights, configuration reference.
- **`.env.example`** — every env var with comments (Neon + MinIO + Aruba
  Object Storage examples).
- **Memories** at `~/.claude/projects/-Users-gzileni-Git-limen/memory/`:
  - `deploy-target` — Aruba VPS + Docker, no cloud.
  - `object-store-design` — Protocol, filesystem + s3-compatible, Azure
    removed.
- **Project doc**: `Limen_Project_Document.md` (when present at repo root)
  is the authoritative architectural reference for phases beyond the
  current scaffold.
