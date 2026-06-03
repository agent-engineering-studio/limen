# Limen

> **AI multi-factor landslide-risk monitoring for the Italian territory.**
> Pilot regions: **Puglia + Basilicata**.

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-green.svg)](./LICENSE)
[![uv](https://img.shields.io/badge/managed%20by-uv-261230)](https://github.com/astral-sh/uv)
[![ruff](https://img.shields.io/badge/lint-ruff-261230)](https://github.com/astral-sh/ruff)
[![mypy --strict](https://img.shields.io/badge/typed-mypy%20--strict-blue)](http://mypy-lang.org/)

Limen ("threshold" in Latin) fuses **morphology, geology, soil moisture,
rainfall, seismicity and historical inventories** to produce a per-cell
landslide-risk score for any AOI in Italy. The system is built around a
Multi-Agent Framework (MAF) that orchestrates ingestion → scoring →
explanation, with a Postgres+PostGIS data layer that is portable between
local Docker, Neon (serverless), and any managed PostgreSQL.

This repository currently contains **Phase 0 (scaffolding) + Phase 1 (data
layer) + Phase 2 (external integrations + static-feature bootstrap) +
Phase 3 (deterministic V1 scoring engine + calibrate / backtest CLIs) +
Phase 4 (MAF agents & workflow: 10 custom executors, RiskAnalyst /
Briefing ChatAgents, `limen monitor-once` runner)**. Later phases add a
FastAPI gateway, a map-first frontend, notifications, IoT ingestion, and
the V2 ML engine.

The V1 engine is a **pure**, interpretable, weighted-linear combination
(§2.4 of the project doc) reading every weight, threshold, and class
cutoff from [`src/limen/config/regional_thresholds.yaml`](./src/limen/config/regional_thresholds.yaml).
No magic numbers in the scoring code. No LLM. No I/O. The same
`CellFeatureBundle` interface will accept the V2 ML drop-in later.

| Source | What we ingest | Cadence | Implementation |
|---|---|---|---|
| **Open-Meteo** | hourly precip, soil moisture 0–7 / 7–28 cm, snowfall, snow depth (forecast); cumulated precip 30/60/90 d (ERA5 archive) | live, cache 30 min | `integrations/openmeteo/` + `CachedOpenMeteoClient` |
| **ISPRA IdroGEO** | IFFI (points/polys/lines), PAI hazard, susceptibility | weekly batch | `integrations/idrogeo/` + idempotent `sync_job` keyed by content hash |
| **INGV** | FDSN events (mag ≥ 3.5, last 7 d, AOI bbox); ShakeMap `grid.xml` raster | event-driven poll | `integrations/ingv/` + `seismic_repo` + `ObjectStore` |
| **EFFIS** | burnt-area perimeters; dNBR (when programmatic — currently manual data request, marked TODO) | weekly batch | `integrations/effis/` |
| **Static bootstrap** | `iffi_density_500`, `distance_to_iffi_m`, `pai_class_norm` per cell — set-based PostGIS SQL | one-shot CLI | `integrations/static_bootstrap/` + `limen bootstrap-static` |
| **Scoring engine (V1)** | Caine I/D excess, API sigmoid, post-fire window, seismic decay, weighted aggregator + 5-class | pure (no I/O) | `core/scoring/` + `MultiFactorScoringEngine` |
| **Calibrate** | Per-AOI min/max norm stats; precompute `s_static`; **S vs ISPRA correlation gate (≥ 0.85)** | one-shot | `limen calibrate` + `reports/calibrate_<aoi>.md` |
| **Backtest** | Replay any historical window with Open-Meteo ERA5 + IFFI truth set → hit rate / FAR / lead time vs §2.5 targets | one-shot | `limen backtest` + `reports/backtest_*.md` + `data/notebooks/02_backtest_oct2018.ipynb` |
| **MAF workflow (V1)** | AreaResolver → StaticFactors → MeteoFetch → SeismicCheck → FireCheck → \[SensorFetch?\] → RiskScoring → EscalationGate → RiskAnalyst → Briefing → PersistResult → AlertDispatch | one-shot CLI | `agents/` + `limen monitor-once` |
| **LLM providers** | Anthropic > OpenAI > Foundry > Ollama (resolved by env precedence; cloud key always wins over Ollama). Briefing in Italian (150–250 parole). RiskAnalyst returns strictly-typed JSON. | resolved at startup | `agents/llm_factory/resolve_llm_factory` |

---

## Table of contents

- [Why these decisions](#why-these-decisions)
- [Architecture (current phase)](#architecture-current-phase)
- [Quickstart](#quickstart)
- [Project layout](#project-layout)
- [Configuration reference](#configuration-reference)
- [Database schema highlights](#database-schema-highlights)
- [LLM provider precedence](#llm-provider-precedence)
- [Testing](#testing)
- [Quality gates](#quality-gates)
- [Roadmap (out of scope for this phase)](#roadmap-out-of-scope-for-this-phase)
- [License](#license)

---

## Why these decisions

| Decision | Rationale |
|----------|-----------|
| **Engine-agnostic PostgreSQL 16 + PostGIS** (no Supabase, no BaaS, no ORM) | Same SQL, same code path on local Docker, Neon, RDS, Cloud SQL, or self-hosted. Only `DB__CONNECTION_STRING` changes. |
| **`asyncpg` + custom PostGIS codec** | Geometries flow as Shapely objects, no `ST_AsBinary`/`ST_GeomFromWKB` boilerplate, no ORM session lock-in. |
| **`pg_cron` is optional** | Neon doesn't support it. The in-process **APScheduler** runs the same periodic jobs when the extension is absent. Pick with `SCHEDULER__CACHE_CLEANUP={pg_cron,apscheduler}`. |
| **Object storage behind a Protocol** (`filesystem` / `s3`) | Raster bytes never go in the DB. PostGIS stores references (path + bbox + CRS + checksum) only. The `s3` backend targets any S3-compatible endpoint (MinIO sidecar, Aruba Cloud Object Storage, R2, B2) via `OBJECT_STORE__ENDPOINT_URL` — not just AWS. |
| **Plain-SQL migrations** | No Alembic, no Django ORM. A 60-line runner with a `schema_migrations` table + checksums. Identical behaviour on every Postgres. |
| **Pydantic v2 + `structlog`** | Strict typed configuration and structured logs without rolling our own. |
| **`uv` + `src/` layout** | Fast, lockfile-first dependency management. The package can't import its own test code by accident. |

---

## Architecture (current phase)

```
                       ┌──────────────────────┐
                       │ limen CLI            │
                       │  migrate / seed      │
                       └──────────┬───────────┘
                                  │ asyncpg + PostGIS codec
                ┌─────────────────┴─────────────────┐
                │  PostgreSQL 16 + PostGIS 3.5      │
                │  ─ aoi, grid_cells, susceptibility│
                │  ─ iffi_landslides, pai_hazard    │
                │  ─ risk_assessments               │
                │  ─ raster_refs, app_cache         │
                │  ─ schema_migrations              │
                │                                   │
                │  pg_cron jobs (when available)    │
                │      ⇅ falls back to ⇅            │
                │  APScheduler (in-process)         │
                └───────────────────────────────────┘
                                  ▲
                ObjectStore Protocol (DB stores only refs)
                ┌─────────────────┴─────────────────┐
                │ filesystem │ S3-compatible        │
                │            │ (MinIO, Aruba OS,    │
                │            │  R2, B2 — via        │
                │            │  endpoint_url)       │
                └────────────────────────────────────┘
```

The data layer is **identical between local Docker and Neon**. Only
`DB__CONNECTION_STRING` (and `SCHEDULER__CACHE_CLEANUP=apscheduler` on
Neon) differ. The grid generator reprojects to EPSG:3035 (LAEA Europe) so
that 1 km cells are actually 1 km, then writes them back in EPSG:4326.

---

## Quickstart

### 1. Install

```bash
make install     # = uv sync --all-groups
```

Requires Python 3.12+ and [uv](https://github.com/astral-sh/uv). For
integration tests you also need Docker.

### 2. Pick your Postgres

#### Option A — local Docker (default)

```bash
make up-dev                          # Postgres 16 + PostGIS 3.5 + pg_cron + pgvector
make seed                            # migrations + Puglia/Basilicata AOIs + ~60k 1 km cells
uv run limen bootstrap-static        # IFFI density / distance + PAI normalised class
uv run limen calibrate               # s_static + per-AOI norm stats; S vs ISPRA gate
uv run limen backtest                # §2.5 metrics report for Oct 2018 (default window)
uv run limen monitor-once            # full MAF workflow once per AOI
```

#### Option B — Neon (serverless Postgres)

1. Create a Neon project and branch.
2. Put in `.env`:

   ```env
   DB__CONNECTION_STRING=postgresql://user:password@ep-xxxx.aws.neon.tech/limen?sslmode=require
   SCHEDULER__CACHE_CLEANUP=apscheduler
   ```

3. Run the same command — **no code change required**:

   ```bash
   uv run limen seed
   ```

   The `pg_cron` extension is silently skipped (it doesn't exist on Neon),
   and the in-process APScheduler takes over the periodic jobs.

#### Option C — Apple Silicon dev

The official `postgis/postgis` image does not currently publish an arm64
manifest. The integration tests automatically pick
[`imresamu/postgis-arm64`](https://hub.docker.com/r/imresamu/postgis-arm64).
Override with `LIMEN_TEST_POSTGIS_IMAGE` if you prefer a different one.

### 3. Run tests

```bash
make test                  # unit + integration
make test-unit             # fast: no Docker required
make test-integration      # spins up Postgres+PostGIS via testcontainers
```

---

## Project layout

```
src/limen/
├── cli/                # `limen` console script
│   ├── main.py         # dispatcher
│   ├── migrate.py      # `limen migrate`
│   └── seed.py         # `limen seed`
├── config/
│   └── settings.py     # pydantic-settings (DB, OBJECT_STORE, LLM, SCHEDULER)
├── core/
│   ├── logging.py      # structlog configuration
│   ├── scheduling.py   # APScheduler (Neon path)
│   └── llm_resolver.py # provider precedence resolver (stub for later phases)
└── data/
    ├── db.py           # asyncpg pool + PostGIS hex-EWKB codec
    ├── migrate.py      # idempotent SQL migrations runner (schema_migrations)
    ├── migrations/
    │   ├── 001_extensions.sql       # postgis (req), pgvector (opt), pg_cron (opt)
    │   ├── 002_core_tables.sql      # aoi, grid_cells, iffi, pai, risk, …
    │   ├── 003_cache_table.sql      # app_cache + pg_cron job (when available)
    │   └── 004_raster_refs.sql      # raster references (paths + bbox + checksum)
    ├── object_store/   # filesystem | s3-compatible behind a Protocol
    ├── caching/        # PostgresCache (DistributedCache Protocol)
    ├── repos/          # aoi_repo, grid_repo (+ iffi, susceptibility, assessment stubs)
    └── seed/
        ├── puglia_aoi.geojson       # placeholder coarse outline (TODO: ISTAT)
        ├── basilicata_aoi.geojson   # placeholder coarse outline (TODO: ISTAT)
        └── loader.py
infra/
├── postgres/Dockerfile.db          # postgis/postgis:16-3.5 + pg_cron + pgvector
└── docker/docker-compose.dev.yml
tests/
├── unit/                            # config, LLM resolver, FS store, seed loader
└── integration/                     # PostgresCache TTL + p95<10ms + repos + idempotency
```

---

## Configuration reference

Configuration is loaded from environment variables (and optional `.env`)
via `limen.config.settings.Settings`. Nested fields use `__` as delimiter.

| Variable | Default | Notes |
|----------|---------|-------|
| `DB__CONNECTION_STRING` | `postgresql://limen:limen@localhost:5432/limen` | PostgreSQL DSN. Add `?sslmode=require` for Neon. |
| `DB__POOL_MIN_SIZE` / `DB__POOL_MAX_SIZE` | `2` / `20` | asyncpg pool sizing. |
| `DB__STATEMENT_CACHE_SIZE` | `1024` | asyncpg prepared-statement cache. Set `0` on PgBouncer (transaction pool). |
| `OBJECT_STORE__BACKEND` | `filesystem` | `filesystem` or `s3`. |
| `OBJECT_STORE__ROOT` | `./object_store_root` | Filesystem root. |
| `OBJECT_STORE__BUCKET` / `__PREFIX` / `__REGION` / `__ENDPOINT_URL` / `__ACCESS_KEY_ID` / `__SECRET_ACCESS_KEY` | _empty_ | S3-compatible settings. Set `__ENDPOINT_URL` for MinIO, Aruba Cloud Object Storage, R2, B2. |
| `SCHEDULER__CACHE_CLEANUP` | `apscheduler` | `pg_cron` or `apscheduler`. **Use APScheduler on Neon.** |
| `SCHEDULER__CACHE_CLEANUP_INTERVAL_SECONDS` | `300` | APScheduler tick. |
| `LLM__PROVIDER` | _empty_ | Optional override: `anthropic` / `openai` / `foundry` / `ollama`. |
| `LLM__OLLAMA_BASE_URL` | `http://localhost:11434` | Local LLM fallback. |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `FOUNDRY_ENDPOINT` + `FOUNDRY_API_KEY` | _empty_ | Auto-detected (see [LLM provider precedence](#llm-provider-precedence)). |
| `LOG_LEVEL` | `INFO` | structlog log level. |
| `LOG_JSON` | `false` | Set `true` in production for JSON logs. |

See [`.env.example`](./.env.example) for the canonical reference.

---

## Database schema highlights

All geometries are stored in **EPSG:4326**. Distances/areas are computed by
re-projecting to a metric CRS in application code (EPSG:3035 for Italy).

| Table | Purpose |
|-------|---------|
| `dataset_versions` | Single registry of external dataset versions (IFFI, PAI, climate reanalyses…). Other tables reference this for reproducibility. |
| `aoi` | Areas of Interest (regions, municipalities, project polygons). `bbox` is generated. GiST on `geom` and `bbox`. |
| `grid_cells` | 1 km² discretisation per AOI. Deterministic ID = `<aoi_id>|<row>|<col>`. Centroid generated. GiST on geom and centroid. |
| `iffi_landslides` | ISPRA Inventario dei Fenomeni Franosi in Italia. |
| `pai_hazard` | Piano di Assetto Idrogeologico hazard polygons. |
| `susceptibility` | Pre-computed per-cell susceptibility (0..1 + class). |
| `cell_static_factors` | Per-cell slope, aspect, elevation, TWI, lithology, land cover, distance-to-IFFI… |
| `risk_assessments` | Output of the scoring engine + MAF agents (horizon + score + factors + explanation + dataset versions). |
| `raster_refs` | References to raster bytes living in the ObjectStore (path + bbox + CRS + checksum). |
| `app_cache` | UNLOGGED key/value JSONB cache with TTL. Cleaned up by `pg_cron` or APScheduler. |
| `schema_migrations` | Applied-migrations registry with SHA-256 checksums (idempotency guard). |

---

## LLM provider precedence

For phases that actually use LLMs (scoring explanations, MAF agents) the
provider is resolved by `limen.core.llm_resolver.resolve_provider`:

1. `LLM__PROVIDER` override → wins unconditionally.
2. `ANTHROPIC_API_KEY` present → **Anthropic**.
3. `OPENAI_API_KEY` present → **OpenAI**.
4. `FOUNDRY_ENDPOINT` + `FOUNDRY_API_KEY` present → **Microsoft Foundry**.
5. Otherwise → **Ollama** (local fallback at `LLM__OLLAMA_BASE_URL`).

A cloud key always wins over Ollama unless `LLM__PROVIDER=ollama` is set
explicitly.

---

## Testing

```bash
make test-unit          # 14 tests, no Docker, < 1s
make test-integration   # 8 tests, needs Docker, ~5s once the image is cached
make test               # all 22
```

Integration tests spin up a real PostgreSQL+PostGIS via `testcontainers`,
apply the migrations, exercise the AOI + grid repositories on a tiny
~5 km × 5 km polygon near Bari, assert migrations are idempotent, and
verify that `PostgresCache.get_json` has **p95 < 10 ms** on the local
container.

---

## Quality gates

| Tool | Where |
|------|-------|
| `ruff check` / `ruff format` | `make lint`, `make format` |
| `mypy --strict` | `make typecheck` — all of `src/` |
| `pytest -q` | `make test` — unit + integration |
| `pre-commit` | end-of-file-fixer, trailing-whitespace, ruff, mypy |
| Conventional commits | enforced by convention, not tooling |

---

## Roadmap (out of scope for this phase)

The following land in **later prompts**, each behind clean extension points
already in this repo:

- **FastAPI gateway** (Phase 5): REST + tile endpoints, OpenAPI schema,
  APScheduler hourly job.
- **Frontend** (Phase 6): map-first SPA with risk overlays, time controls,
  and explainability drill-downs.
- **Notifications** (Phase 7): alerting on score-crossing events.
- **IoT ingestion** (V1.5): real-time sensor streams.
- **ML / MLOps** (V2): trainable susceptibility model, model registry,
  drift monitoring.
- **DEM / CORINE / ISPRA Carta Geologica ingest** to fill the currently-NULL
  `cell_static_factors` columns (`slope_deg`, `aspect_deg`, `curvature`,
  `twi`, `elevation_m`, `landuse_code`, `lithology`, `litho_weight`,
  `dist_faults_m`). The static-bootstrap pipeline already logs
  `static_bootstrap.skip` for each missing component.

---

## License

Apache-2.0 — see [LICENSE](./LICENSE).
