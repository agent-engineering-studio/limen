<p align="center">
  <img src="docs/images/banner.png" alt="Limen — Landslide Monitoring Framework" width="100%">
</p>

# Limen

🇬🇧 **English** · 🇮🇹 [Italiano](./README.it.md)

> **AI monitoring of landslide, flood and wildfire danger across Italy,
> cell by cell, now and over the next 72 hours.**
> **National coverage — all 20 ISTAT regions** on a 1 km² grid
> (~312k cells), open data only, EUPL-1.2 code.
>
> 🗺️ **Live map:** <https://limen.agentengineering.it/> (Italian and English) ·
> ☕ **[Support Limen](#support-limen)** on [Buy Me a Coffee](https://www.buymeacoffee.com/f9t3zol)

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: EUPL-1.2](https://img.shields.io/badge/license-EUPL--1.2-green.svg)](./LICENSE)
[![uv](https://img.shields.io/badge/managed%20by-uv-261230)](https://github.com/astral-sh/uv)
[![ruff](https://img.shields.io/badge/lint-ruff-261230)](https://github.com/astral-sh/ruff)
[![mypy --strict](https://img.shields.io/badge/typed-mypy%20--strict-blue)](http://mypy-lang.org/)

Limen (Latin for "threshold") combines **morphology, geology, soil
moisture, rainfall, seismicity, wildfires and historical archives** into a
danger score for **three hazards** on every 1 km² cell of Italy, every hour,
with a 72-hour forecast:

- **Landslides**: terrain susceptibility (IFFI, PAI, slope, lithology)
  times rainfall against Caine's intensity-duration thresholds, plus recent
  earthquakes and wildfires.
- **Floods**: ISPRA hydraulic hazard times the stronger of the pluvial
  branch (forecast rain plus rain already fallen, from the DPC radar-gauge
  merge) and the fluvial branch (GloFAS discharge against that watercourse's
  own ordinary high flow).
- **Wildfires**: the Canadian Fire Weather Index (Van Wagner), computed per
  weather node and modulated by fuel and slope.

The numbers come from a deterministic, readable engine; the AI writes the
per-region narratives and never changes a number. Stack: Python 3.12 +
FastAPI + PostgreSQL 16 + PostGIS, a Vite + React + MapLibre frontend, and
multi-channel notifications. The system is built around a Multi-Agent
Framework (MAF) that orchestrates ingestion → scoring → explanation, with a
data layer portable across local Docker, Neon (serverless) and any managed
PostgreSQL.

## Quick start

```bash
git clone https://github.com/agent-engineering-studio/limen.git
cd limen
uv sync --all-groups
make up                     # Postgres+PostGIS + GeoServer (mcp-geoserver) + frontend
make init                   # migrate → seed 20 regions → ITALICA → bootstrap → calibrate
uv run limen serve          # FastAPI on http://localhost:8080/docs
uv run limen report build   # static HTML report of the riskiest zones → site/index.html
( cd frontend && npm ci && npm run dev )   # map on http://localhost:5173
```

`make init` is idempotent and rebuilds all the data on a fresh machine: it
applies the migrations, seeds the 20 ISTAT regions (1 km² grid), downloads
the **e-ITALICA** landslide catalogue from Zenodo (the §2.5 backtest truth
set), fills the per-cell static factors (IFFI + PAI from the GeoServer
PostGIS, slope from the DTM) and calibrates `s_static`.

On **Neon** (serverless dev/test): set `DB__CONNECTION_STRING` with
`?sslmode=require` and `SCHEDULER__CACHE_CLEANUP=apscheduler`, nothing else —
`pg_cron` is skipped and the in-process APScheduler takes over the periodic
jobs. In **production** (self-hosted Docker host, no cloud provider):
`docker compose -f infra/docker/docker-compose.demo.yml up -d --build`. The
LLM provider is resolved by precedence `LLM__PROVIDER` >
`ANTHROPIC_API_KEY` > `OPENAI_API_KEY` > Foundry credentials > llama.cpp.
In production all LLM traffic goes through the **LiteLLM** gateway
(`:8091`): local models run on llama.cpp / llama-swap, and the regional
narratives (`LLM__MODELS__BRIEFING=quality-cloud`) on **Claude Sonnet 5.5**.
The inference stack can be reproduced in containers: see
[`docs/inference.md`](./docs/inference.md).

**Not a developer?** The plain-language documentation in
[`docs/divulgazione/`](./docs/divulgazione/README.md) (Italian) explains
without jargon how each cell's risk is computed, what the ML model and the
AI agents do (and do not do), which open sources the data come from, and why
the LLM runs on our own server. In the SPA, the **How it works** page
(`#/come-funziona`) gathers the whole engine on one page — data, formulas,
forecast, ML, AI, geography: its source is
[`docs/guida/limen.md`](./docs/guida/limen.md).

Further reading: [`docs/demo.md`](./docs/demo.md) (local demo on a small AOI),
[`docs/architecture.md`](./docs/architecture.md),
[`docs/openclaw.md`](./docs/openclaw.md),
[`docs/api.md`](./docs/api.md),
[`docs/deployment.md`](./docs/deployment.md),
[`docs/scoring-model.md`](./docs/scoring-model.md),
[`docs/runbook.md`](./docs/runbook.md),
[`docs/divulgazione/`](./docs/divulgazione/README.md) (for a non-technical audience).

The V1 engine is a **pure**, interpretable weighted combination (§2.4 of the
project document) that reads every weight, threshold and class cutoff from
one YAML file per hazard in
[`src/limen/config/hazards/`](./src/limen/config/hazards/) — named after the
enum value (`landslide.yaml`, `flood.yaml`, `wildfire.yaml`). No constants
hard-coded in the scoring code. No LLM. No I/O. The same
`CellFeatureBundle` interface also accepts the V2 ML engine.

The architecture is **multi-hazard**: `hazard_type` runs through tables,
views, API, MCP and A2A, and each hazard brings its own thresholds file, its
own schema and its own engine, registered per *(hazard, implementation)*.
All three — landslide, flood (#63) and wildfire (#61) — are enabled in
production; adding a fourth is a YAML file plus a registration, without
touching workflow, API or persistence.

---

## Components and sources

| Source | What we ingest | Cadence | Implementation |
|---|---|---|---|
| **Open-Meteo** | hourly precipitation, soil moisture 0–7 / 7–28 cm, snow (forecast); accumulated precipitation (archive). Served by **our own instance** (compose profile `meteo`): the public API's 10,000 calls/day were exhausted by the sweep and left flood and wildfire at zero across Italy (#142) | live, 30 min cache | `integrations/openmeteo/` + `CachedOpenMeteoClient` |
| **ISPRA (GeoServer PostGIS)** | IFFI inventory (landslides/areas/DGPV, all regions), PAI landslide mosaic; the hydraulic mosaic feeds the flood susceptibility and the landslide `H` component | at init / weekly | `integrations/geoserver_source/` reads the mcp-geoserver PostGIS |
| **Copernicus EWDS — GloFAS** | per-node river discharge: the operational forecast (`cems-glofas-forecast`, control run) downloaded ahead of the per-cell forecast, and each node's **ordinary high flow** from the multi-year history (`glofas_riferimento`), the denominator of the fluvial ratio. Without `COPERNICUS__EWDS_KEY` it falls back to Open-Meteo's GloFAS | forecast 4×/day, references nightly | `integrations/copernicus/` + `glofas_previsione` / `glofas_riferimento` |
| **Copernicus Land — EGMS** | Ortho L3 ground motion (Sentinel-1, 100 m, vertical and east-west): per-cell p90 velocity and the number of valid pixels. Downloaded with the CLMS service key; a nightly step checks whether a new release is out | yearly sync + nightly release check | `integrations/egms/` + `limen sync-egms` |
| **DPC radar** | national SRI (1 km / 5 min) as a nowcast trigger, and the radar-gauge **«Merging»** accumulation, read at each cell centroid so a storm in progress counts in the flood score (#199) | every `NOWCAST__INTERVAL_MINUTES` / per sweep | `integrations/dpc/` |
| **INGV** | FDSN events (mag ≥ 3.5, last 7 days, AOI bbox); ShakeMap grid | event-driven polling | `integrations/ingv/` + `seismic_repo` + `ObjectStore` |
| **EFFIS** | burnt-area perimeters (a public **MapServer**, no credentials); bulk Shapefile fallback | weekly batch | `integrations/effis/` |
| **Static bootstrap** | per cell: `iffi_density_500` (within 500 m of the cell), `distance_to_iffi_m`, `pai_class_norm`, `slope_deg` (DTM) — set-based PostGIS SQL. Steps whose source has not changed are skipped (#101) | one-shot CLI | `integrations/static_bootstrap/` + `limen bootstrap-static` |
| **Scoring engine (V1)** | Caine I/D threshold (re-fitted on ITALICA), sigmoid API, post-fire window **modulated by burn severity** (FIRMS FRP density: the sum correlates with burnt area at 0.63 and the density at 0.26, so the sum measures the size of the fire, not its intensity), seismic decay, weighted aggregator + 5 classes | pure (no I/O) | `core/scoring/` + `MultiFactorScoringEngine` |
| **Hazard dimension** | `hazard_type` on every risk row and on both dedup ledgers; engines registered per *(hazard, implementation)* pair; one thresholds file per hazard. Three enabled: `landslide`, `flood`, `wildfire` | cross-cutting | `core/models/hazard.py`, `core/scoring/registry.py`, `config/hazards/` |
| **Calibrate** | per-AOI normalisation stats; precompute `s_static` | one-shot | `limen calibrate` + `reports/calibrate_<aoi>.md` |
| **Event ingest** | the **e-ITALICA** catalogue (rainfall-triggered, dated landslides, all of Italy) — the backtest truth set | one-shot, auto-download from Zenodo | `limen ingest-events` |
| **Fire history** | the **FIRMS per-country archive** (MODIS since 2000, VIIRS S-NPP since 2012): 391,987 Italian detections → 224,156 cell-day events and `fire_density` on 65,771 cells. Public, no credentials — the download portal asks for Earthdata and delivers by e-mail, but the per-country archives are plain CSV. Only `type = 0`: without that filter the most "burnt" cell in Italy was the ILVA steelworks in Taranto with 3,308 fire-days, because a steelworks is a high-confidence detection. Sanity check: 16 EFFIS perimeters out of 16 confirmed by a hotspot within 1 km / ±2 days | one-shot, cached | `integrations/firms/archive.py` + `limen ingest-fire-history` |
| **Wildfire ML challenger** | a **per-hazard** feature schema (FWI/ISI/DC from the rebuilt chain, CLC fuel, WUI proximity, fire memory, slope, 30-day rain), case-control pseudo-absences, spatial-block CV, a SHA of the matrix for reproducibility. Measured on one season (30,066 samples, 222 blocks): AUC-PR **0.352** against **0.237** for the FWI-only baseline; Random Forest 0.367, logistic 0.284. V1 stays champion; promotion is manual | one-shot | `ml/fire_features.py` + `LIMEN_TRAIN_HAZARD=wildfire limen train` |
| **Flood truth set** | **observed flooded** perimeters from Copernicus EMS Rapid Mapping (13 Italian activations, 9,463 polygons, 480 km², 2,354 cells over 9 regions) plus the **observation masks**, which say where the satellite looked: inside, the absence of a polygon is an observed "not flooded"; outside, an alert is *unverifiable*, not false. Public, no credentials — FloodCat needs a DPC account and Polaris publishes PDFs | one-shot, vector cache | `integrations/copernicus_ems/` + `limen ingest-events --hazard flood` |
| **Flood backtest** | daily-step replay with the forecast **as issued** (`issued`, the operational skill) next to the rain that then fell (`observed`, the ceiling with a perfect forecast) → hit rate, **base rate**, FAR on observed cell-days only, lead time | one-shot | `limen backtest-flood` + `reports/backtest_flood_*.md` |
| **Backtest** | replay of a historical window with antecedent rainfall + the e-ITALICA truth set → hit rate / FAR / lead time against the §2.5 targets | one-shot | `limen backtest` + `reports/backtest_*.md` |
| **MAF workflow (V1)** | AreaResolver → StaticFactors → MeteoFetch → SeismicCheck → FireCheck → \[SensorFetch?\] → RiskScoring → EscalationGate → RiskAnalyst → Briefing → PersistResult → AlertDispatch | one-shot CLI | `agents/` + `limen monitor-once` |
| **LLM providers** | precedence `LLM__PROVIDER` > Anthropic > OpenAI > Foundry > **llama.cpp**; the resolver skips cloud providers without an SDK and falls back to llama.cpp (httpx only). Ollama stays selectable with `LLM__PROVIDER=ollama`. Narratives in Italian and English; RiskAnalyst returns typed JSON | resolved at startup | `agents/llm_factory/resolve_llm_factory` |
| **HTTP API** | `/health` + `/ready`, `GET /api/aoi/{id}/risk/latest`, `GET /api/cell/{id}/breakdown`, `GET /api/aoi`, `GET /api/alerts`, `/api/comuni`, `/api/regioni`, `/api/tiles/...`, OpenAPI on `/docs` and `/redoc` | FastAPI / uvicorn | `api/` + `limen serve` |
| **Scheduled jobs** | three cadences (#78), in the separate `limen worker` process: **hourly** sweep (V1 scoring, persistence, alerts — no LLM); **asynchronous** regional narratives; **nightly** run (shadow ML, drift, retrain, partitions, retention, GloFAS references, EGMS release check). The per-cell 72-hour forecast runs at 02/08/14/20 UTC on the latest weather runs; **DPC radar nowcast** every 15 min, **NASA FIRMS hotspots** every 45 min, daily national report, weekly ISPRA sync | APScheduler in the worker | `api/jobs/` |
| **DPC radar (nowcast)** | national SRI 1 km / 5 min (DPC radar platform, CC-BY-SA): rain ≥ `NOWCAST__MIN_INTENSITY_MMH` over a region ⇒ that AOI's workflow starts at once instead of waiting for the hourly tick (45 min cooldown; alerts follow the normal operational path) | poll every `NOWCAST__INTERVAL_MINUTES` | `integrations/dpc/` + `api/jobs/nowcast_monitoring.py` |
| **NASA FIRMS hotspots** | active VIIRS 375 m (S-NPP / NOAA-20 / NOAA-21) and MODIS 1 km detections with ~3 h NRT latency: `FIRMS__MIN_HOTSPOTS` hotspots inside an AOI ⇒ immediate workflow (cooldown `FIRMS__COOLDOWN_MINUTES`), and `months_since_fire` — hence the post-fire F factor — activates within hours instead of waiting for the EFFIS perimeter. Fail-closed: without `FIRMS__MAP_KEY` the feed is inert and the job is not registered | poll every `FIRMS__INTERVAL_MINUTES` (1 transaction per source over the national bbox) | `integrations/firms/` + `api/jobs/firms_monitoring.py` + `limen firms-sync` |
| **Predictive forecast** | scoring at `now+H` hours with Open-Meteo forecast rain (observed + forecast in the same window); champion + ML challenger on the same cells; on-demand report or a scheduled "FORECAST" alert with (AOI, horizon) dedup | `limen forecast` / job every `FORECAST__INTERVAL_HOURS` | `agents/workflows/forecast.py` + `api/jobs/forecast_monitoring.py` |
| **MCP `limen-ops`** | `tool_risk_summary`, `tool_top_risk_cells`, `tool_cell_breakdown`, `tool_recent_alerts`, `tool_national_report`, `tool_comune_risk`, `tool_top_comuni` + admin tools (`tool_run_monitor`, `tool_build_report`, `tool_forecast_history`, fail-closed on `MCP_ADMIN_TOKEN`) for agent gateways (OpenClaw, Claude Desktop) | compose service `mcp`, HTTP `127.0.0.1:8766/mcp` | `mcp/` + `limen mcp-serve` |
| **A2A (Agent2Agent)** | JSON-RPC 2.0 interoperability with other agents: Agent Card at `/.well-known/agent-card.json`, `/a2a` endpoint with `message/send`, `message/stream` (SSE), `tasks/get`/`cancel`, push notifications; skills = the read-only queries of `limen-ops`; tasks persisted (`a2a_tasks`) | mounted on the API, read-only | `a2a/` + `api/endpoints/a2a.py` + UI page `#/integrazioni` |
| **Daily national report** | aggregated picture of the 20 regions (per-region summary, top national cells, top shadow-ML cells, 24 h alert counts) rendered in deterministic Italian and sent every morning on the notification channels | cron `REPORT__HOUR_UTC` (default 06 UTC) | `api/jobs/daily_report.py` + `tool_national_report` |
| **Static HTML report** | a page of the *highest-risk zones*: clusters of contiguous cells (PostGIS `ST_ClusterDBSCAN`), an **interactive Leaflet mini-map per zone** (real zoom/pan on an OSM/Carto basemap, cells as GeoJSON, **geographic coordinates** highlighted), a deterministic S/M/E/F/H reason + verdict, YlOrRd palette. No LLM, no raster images. It tries the alert threshold (`High`) and, if **no** zone exceeds it, steps down (`Moderate`→`Low`) and still shows the relatively riskiest areas with an informative banner (no alarm) — the report is never empty. **Immutable versioned archive** (`site/archive/<ts>/` + `manifest.json`) for later fact-checking; idempotent (skips the rebuild if the assessment has not changed); publishable via GitHub Pages (`REPORT__HTML_PUBLISH`) | at boot + every `REPORT__HTML_INTERVAL_HOURS` (default 1 h) or on demand | `site/` + `limen report build` + `api/jobs/html_report.py` |
| **Vector tiles** | materialised view `mv_latest_risk` (grid cells × enabled hazards ⨝ latest assessment per cell and hazard), refreshed by `refresh_mv_latest_risk()`; served by **pg_tileserv**, with `risk_at(...)` for any hazard and `forecast_at(...)` for the 72-hour timeline | per monitoring cycle | migrations `007_map_views.sql`, `060_forecast_tiles.sql` |
| **Per-comune rollup** | administrative aggregation `mv_comune_risk`, one row per comune and hazard: class of the **worst cell** + profile (counts per class, exposure) + ranking by exposure. Surfaces: map (comune choropleth + alert-cell badge on High+, drill-down), sidebar, ranking, REST `/api/comuni` + `/api/comune/{istat}`, MCP/A2A tools `top_comuni`/`comune_risk`, report section, comune in alerts. ISTAT boundaries imported with `limen seed-comuni`; refresh chained to `refresh_mv_latest_risk()` | one-shot `seed-comuni` + per cycle | migration `026_comuni.sql` + `data/repos/comune_risk.py` |
| **Frontend** | Vite + TS + React + **MapLibre GL JS** SPA in **Italian and English** (`?lang=en`, remembered choice or browser language): risk map with one five-class ramp for all hazards (checked for colour-blind contrast on the dark basemap), legend with labels and ranges (not colour only), 72-hour timeline, alerts, comuni ranking, regional narratives, «Verifiche» fact-check articles, opt-in PAI/IFFI PMTiles overlays | public, read-only | `frontend/` |
| **Notifications** | `NotificationChannel` protocol + Telegram / MQTT / Email / **Webhook** (JSON POST to agent gateways, e.g. OpenClaw `/hooks` with a bearer token); parallel dispatcher with per-channel exception isolation; dedup on `alert_dispatches` | per workflow tick | `notifications/` |

---

## Why these choices

| Decision | Rationale |
|-----------|-------------|
| **Engine-agnostic PostgreSQL 16 + PostGIS** (no Supabase, no BaaS, no ORM) | Same SQL and same code on local Docker, Neon or self-hosted. Only `DB__CONNECTION_STRING` changes. |
| **`asyncpg` + a custom PostGIS codec** | Geometries travel as Shapely objects: no WKB boilerplate, no ORM session lock-in. |
| **Optional `pg_cron`** | Neon does not support it. The in-process **APScheduler** runs the same periodic jobs when the extension is missing. |
| **Object storage behind a Protocol** (`filesystem` / `s3`) | Raster bytes never go into the DB. PostGIS stores only references (path + bbox + CRS + checksum). The `s3` backend targets any S3-compatible endpoint (MinIO, R2, B2) via `OBJECT_STORE__ENDPOINT_URL` — never a cloud SDK. |
| **Plain SQL migrations** | No Alembic, no ORM. A runner with a `schema_migrations` table + checksums. Identical behaviour on every Postgres. |
| **Pydantic v2 + `structlog`** | Typed configuration and structured logs without reinventing them. |
| **`uv` + `src/` layout** | Lockfile-first dependency management; the package cannot accidentally import its own test code. |
| **GeoServer as a generic data source** | mcp-geoserver publishes the ISPRA open data in its PostGIS; ISPRA semantics live only in the Limen loader, not in the MCP (which stays generic). |
| **Copernicus data directly, not through third-party APIs** | GloFAS from the EWDS and EGMS from the CLMS archive, with our own keys: Open-Meteo cannot host GloFAS, and its cell is one step east of the one it declares (`cella_open_meteo`) — on the Toce, the wrong cell is worth a factor of ten. |

---

## Calibration and validation (§2.5)

The formal test cycle tuned the engine on real data:

- **Caine I/D threshold** re-derived from the **e-ITALICA** catalogue (5,974
  intensity-duration pairs measured by rain gauges), T5 lower envelope per
  macro-region. The historical threshold left 36 % of real landslides below
  threshold; now ~95 % are above it.
- **Backtest rainfall source**: **ERA5** from the self-hosted Open-Meteo
  archive. CERRA (5.5 km) would resolve convective rain better, but the local
  instance does not serve it: its values came back null, were read as 0 mm,
  and the backtest was measuring without rain (#184). Now an archive that
  rains on no node stops the command with `backtest.rainfall.empty`.
- **IFFI density** counted within 500 m of the cell (not of the centroid).
- **Density saturation** in YAML (`static.iffi_density_saturation`),
  balanced on ITALICA (recall vs precision).

Validation against ground truth (real rain-gauge rainfall): ~63–77 % of real
landslides reach ≥ Moderate.

**Where we honestly stand** (#122). With ERA5 rainfall and antecedents as in
production, the **«high»** class still catches few landslides: in Liguria,
November 2019, 11 % of 131 landslides with 0.17 % of cell-hours on alert; in
the Marche, May 2014, none of 172. The score ranks cells well within each
region, but moving the threshold is not enough: a national threshold tuned on
six regions does not hold on the other six, and a per-region threshold does
worse at equal alert rate. The limit lies in the rainfall signal as we read
it today, and that is the next piece of work. The detailed numbers are in the
issue.

---

## Configuration

Loaded from environment variables (and an optional `.env`) via
`limen.config.settings.Settings`. Nested fields use `__` as the delimiter.

| Variable | Default | Notes |
|-----------|---------|------|
| `LIMEN_DATA_ROOT` | the repo's `data/` | One root for the deployment's data (#302): datasets, reports, MLflow artifacts, models, GeoServer data, OSM, imperviousness, radar. Moving Limen = copying this folder and changing this line. Absolute when set; every specific `*_DIR`/`*_RASTER` variable still overrides it. The tree is at the top of `.env.example`. |
| `DB__CONNECTION_STRING` | `postgresql://limen:limen@localhost:5432/limen` | PostgreSQL DSN. Add `?sslmode=require` for Neon. |
| `OBJECT_STORE__BACKEND` | `filesystem` | `filesystem` or `s3`. |
| `OBJECT_STORE__ENDPOINT_URL` | _empty_ | S3-compatible endpoint (MinIO, R2, B2). |
| `SCHEDULER__CACHE_CLEANUP` | `apscheduler` | `pg_cron` or `apscheduler`. **Use APScheduler on Neon.** |
| `SCHEDULER__FORECAST_CELLS_HOURS_UTC` | `[2, 8, 14, 20]` | When the per-cell 72-hour forecast is recomputed. |
| `OPENMETEO__FORECAST_URL` / `__ARCHIVE_URL` | _empty_ | Self-hosted Open-Meteo; empty ⇒ public API. |
| `COPERNICUS__EWDS_KEY` | _empty_ | EWDS key for the GloFAS forecast and references; empty ⇒ GloFAS via Open-Meteo. |
| `EGMS__SERVICE_KEY` | _empty_ | CLMS service key (single-line JSON) for EGMS downloads and the release check. |
| `LLM__PROVIDER` | _empty_ | Override: `anthropic` / `openai` / `foundry` / `ollama` / `llamacpp`. Empty ⇒ llama.cpp unless a cloud key is set. |
| `LLM__LLAMACPP_BASE_URL` | `http://127.0.0.1:8091` | Self-hosted inference gateway (OpenAI shape). **Not** `:8081`, which is GeoServer. From a container: `host.docker.internal`. |
| `LLM__MODELS__<ROLE>` | Claude id | Role → model map. Local engines honour only the roles they declare. Never `quality-local`/`glm52` on a synchronous role: the process refuses to start. See [`docs/inference.md`](./docs/inference.md). |
| `LLM__LLAMACPP_TIMEOUT_SECONDS` | `120` | Ceiling for roles without an override; `LLM__LLAMACPP_ROLE_TIMEOUT_SECONDS` (JSON) per role. |
| `LLM__OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama host (from a container: `host.docker.internal`). |
| `LLM__OLLAMA_MODEL` | `qwen3.6:latest` | Single Ollama model for every agent role. |
| `SCORING__MODE` | `champion_only` | `shadow` runs the ML challenger in parallel (writes `model_runs` only). |
| `FORECAST__ENABLED` | `true` | Scheduled predictive sweep; `FORECAST__HORIZON_HOURS` (48), `__INTERVAL_HOURS` (6), `__MIN_LEVEL` (High). |
| `REPORT__HTML_ENABLED` | `true` | Static HTML report; `__HTML_INTERVAL_HOURS` (1), `__HTML_RUN_AT_STARTUP` (true), `__HTML_OUTPUT_DIR` (site), `__HTML_MIN_LEVEL` (High), `__HTML_MAX_CLUSTERS` (50), `__HTML_ARCHIVE_KEEP` (240), `__HTML_PUBLISH` (false). |
| `NOTIFICATIONS__WEBHOOK__URL` | _empty_ | Agent gateway (OpenClaw `/hooks`); `__TOKEN` for the bearer. |
| `MCP_ADMIN_TOKEN` | _empty_ | Enables the admin MCP tools; unset = disabled (fail-closed). |
| `GEOSERVER_SOURCE__DB_DSN` | _empty_ | DSN of the mcp-geoserver PostGIS (IFFI + PAI). |
| `LIMEN_DEM_RASTER` | _empty_ | DTM GeoTIFF for slope (opt-in). |
| `LIMEN_ITALICA_CSV` | _empty_ | Local e-ITALICA CSV; if absent, auto-download from Zenodo. |
| `LOG_LEVEL` / `LOG_JSON` | `INFO` / `false` | structlog level + JSON output. |

See [`.env.example`](./.env.example) for the full list with examples, and
[`docs/inference.md`](./docs/inference.md) for the LLM engine (gateway
models, role → model map, constraints on synchronous paths).

### Published ports: Docker bypasses ufw

Docker publishes ports by writing to its **own** iptables chains, which are
consulted *before* ufw's: the host's `default deny incoming` does **not**
protect a port published by a container. That is why every `ports:` entry in
the compose files has a bind variable defaulting to `127.0.0.1`
(`LIMEN_PG_BIND`, `LIMEN_API_BIND`, `LIMEN_MQTT_BIND`, `LIMEN_TILESERV_BIND`,
`LIMEN_FRONTEND_BIND`, `LIMEN_MCP_BIND`,
`LIMEN_GEOSERVER_*_BIND`, `LIMEN_GEODATA_*_BIND`).

The ports stay published — not removed — because the documented
`uv run limen migrate/seed/...` workflow connects to them from the host.
Public exposure goes through a reverse proxy on 443 upstream, not by raising
a bind to `0.0.0.0`.

---

## Installing on a new server

Limen needs **only Docker** on the host (#306, epic #308), plus the
repository and a `.env`. The `limen` commands run inside the worker
container; the periodic jobs are in the worker or in their own compose
services, not in the host's crontab.

```sh
git clone https://github.com/agent-engineering-studio/limen.git && cd limen
cp .env.example .env              # at least LIMEN_DATA_ROOT (absolute)
./scripts/nuovo_host.sh --controlla    # prerequisites only, changes nothing
./scripts/nuovo_host.sh --ripristina   # from the nightly backup (needs BACKUP__*)
./scripts/nuovo_host.sh --da-zero      # a fresh stack: seed, events, calibration, FWI
```

`--controlla` checks Docker and Compose, free space under `LIMEN_DATA_ROOT`
(`NUOVO_HOST_DISCO_GB`, 50) and the **fsync latency** of the disk holding
the Docker volumes, measured with `pg_test_fsync` (`NUOVO_HOST_FSYNC_MS_MAX`,
20 ms). The threshold is a lesson already paid for: on a disk at ~1 s per
fsync, `initdb` timed out and every integration test with it.

The other two modes are re-runnable. Both create the folders under
`LIMEN_DATA_ROOT` and the external volumes, and generate
`DB__TILES_PASSWORD` if it is missing. `--ripristina` starts only Postgres,
restores the state (see *Backup and restore*), brings back the sensors CA
when `LIMEN_SENSORI_DIR` is set, then runs `make up`. `--da-zero` runs
`make up`, then `ingest-events`, `calibrate` and `fwi-backfill` in the
worker. Both end with `limen data-status` and `limen jobs`.

**What fills in by itself, and when.** The map: the first hourly sweep,
within the hour. The per-cell forecast: 02, 08, 14 and 20:20 UTC. The FWI
chain needs a month of spin-up after `fwi-backfill` before wildfire numbers
settle; a restore brings it back already settled. The GloFAS references: a
share of nodes every night, weeks for all of them.

### Images: built here or pulled from GHCR

By default the compose files **build** Limen's images on the host
(`limen/api:0.1`, `limen/postgres:16-3.5`, `limen/web:0.1`,
`limen/geodata:0.1`): fifteen minutes, and nothing to say which version is
running. Every push to `main` and every `vX.Y.Z` tag also publishes them on
GHCR (#303), tagged `sha-<commit>`, `main`/`latest` and the version:

```sh
# in .env
LIMEN_IMAGE_PREFIX=ghcr.io/agent-engineering-studio/limen-
LIMEN_IMAGE_TAG=sha-7a8dd95       # or 0.7.0; never latest on a server
```

With the prefix set, `make up` pulls instead of building (`make pull` does
only that), and starts the static SPA instead of the Vite dev server. A
rollback is the previous tag in `.env` and `make up` again. `mcp` runs the
api image, so one tag covers api, worker and mcp; Postgres has the same tag,
so changing it restarts the database container too (the data is in the
volume).

The published SPA calls everything **on its own origin**, so the reverse
proxy in front of it routes `/api/` to the API (`:8080`), `/tiles/` to
pg_tileserv (`:7800`, prefix stripped) and `/geoserver/ispra/wms` to GeoServer
(`:8081`, the WMS path only: the rest of `/geoserver/` is the admin UI). Vite
writes those URLs into the bundle, so a different layout keeps building its
own image (leave `LIMEN_IMAGE_PREFIX` empty). Images are `linux/amd64` only. Third-party
images are pinned to a version (pg_tileserv `20250131`, Open-Meteo `1.6.0`,
mcp-geo-server at its commit), because `latest` on a new host is not what
runs here.

**LLM gateway without a GPU.** `make inference-up-cpu` starts LiteLLM and
the CPU embedding from `infra/docker/docker-compose.inference.yml`, with the
same model names as the GPU stack (`fast`, `chat` and `extract` go to Claude).
Without a cloud key the narrative falls back to the deterministic text; the
map and the alerts never depend on an LLM. Point the API at it with
`LLM__LLAMACPP_BASE_URL=http://litellm:4000` (shared Docker network).

**Not yet in Docker** (#306, still open): the static data loader
(`make static-data` needs `uv` and GDAL on the host) and the reverse proxy
with certificates.

## Backup and restore

Limen backs up its **state** every night, off the server (#304). The
database is about 31 GB, but almost all of it can be rebuilt: the
`risk_assessments` partitions (15 GB, a few days of retention), the ISPRA
layers that reload from their sources (~12 GB), and the outputs of the sweep
and the forecast. What cannot be rebuilt fits in about 2 GB: verified events,
landslide truth, training samples, sensor readings and registrations,
narratives, alert dispatches, `job_runs`, plus the FWI chain and the GloFAS
references, which cost weeks of quota to fill again. Measured on 2026-10-24
against the production data: a **202 MB** dump in **41 s**, restored and
verified on an empty database in **62 s**.

**What is saved.** The `backup` step of the nightly job (`limen-nightly`, one
`job_runs` row with `scope=backup`) writes `backup/<UTC time>/` to a dedicated
S3-compatible bucket (`BACKUP__*` in `.env`, separate from the app's
`OBJECT_STORE__*`):

| File | Content |
|---|---|
| `limen.dump` | `pg_dump --format=custom`: the schema of **every** table, and the data of all of them except `BACKUP__SOLO_SCHEMA` (hot, derived or reloadable tables, which come back empty) |
| `mlflow.dump` | the MLflow registry, when `SCORING__MLFLOW_TRACKING_URI` points at a PostgreSQL database on the same server |
| `ruoli.sql` | `pg_dumpall --roles-only`, without passwords: the restricted roles get theirs from `DB__*_PASSWORD` when the app starts |
| `mlruns.tar.gz` | the folders listed in `BACKUP__CARTELLE` (the MLflow artifacts) |
| `manifest.json` | written last, with sizes, sha256 and the **row count of every saved table**, taken in the same snapshot as the dump: a backup without it was interrupted, and restore ignores it |

Backups older than `BACKUP__RETENTION_GIORNI` (30) are deleted, but the last
`BACKUP__TIENI_ALMENO` (3) complete ones always stay, and a backup with less
than half the state rows of the previous one suspends the deletion (an empty
volume must not push the good backups out of the bucket). If the last successful
backup is older than `BACKUP__ETA_MASSIMA_ORE` (36), the hourly sweep logs
`integration.degraded label=backup.stale`. With no bucket configured the step
is skipped and says so.

The **sensors CA** (`$LIMEN_SENSORI_DIR/ca`) never reaches a container. The
host CLI saves it encrypted (scrypt + AES-256-GCM, passphrase in
`BACKUP__PASSPHRASE_CA`) under `ca-sensori/`, after every `limen sensore
approva`, `revoca` and `cancella-registrante`, or on demand with `limen
sensore backup-ca`. **Keep a copy of the passphrase off the server**: without
it the CA backup cannot be opened, and a lost CA means re-issuing every
sensor certificate.

**Commands**

```sh
make backup                      # a backup now, from the worker
make backup-elenco               # the complete backups on the bucket
make restore CONFERMA=1          # restore the latest one (API and worker stopped)
make restore CONFERMA=1 CHIAVE=backup/2026-10-24T02-05-00Z/
uv run limen sensore ripristina-ca --dove "$LIMEN_SENSORI_DIR"   # on the host
```

**What restore refuses.** A restore that does not find every row the
manifest promises exits with an error, never with "done": `pg_restore` calls
any SQL failure an "ignored error", so only the two known-harmless errors of
`--clean` are accepted (an inherited partition constraint, an extension other
extensions depend on). It also refuses a database with other clients
connected (`make restore` stops API, worker, MCP and the tile server first)
and a database at a different migration than the backup. `--forza` overrides
the last two. The reloadable layers' entries in `dataset_versions` are
forgotten, so their loaders fill them again instead of answering "already
loaded".

**Two things a backup keeps.** The local radar archive
(`RADAR_ARCHIVE__CARTELLA`, ~51 GB) is **not** included: the DPC keeps about
150 days, so add it to `BACKUP__CARTELLE` if the older months matter to you.
And a registrant deleted with `limen sensore cancella-registrante` stays in
the backups until they leave the retention window: a restore older than the
deletion brings the e-mail back, and the deletion must be repeated.

**Restoring on a new server**: `./scripts/nuovo_host.sh --ripristina` does
steps 2–5 below (see *Installing on a new server*). By hand, in this order:

1. Docker, the repository and the `.env`, with the `BACKUP__*` variables and
   the CA passphrase.
2. Start only the database: `make db-up` (an empty `limen` database, as the
   image creates it).
3. `make restore CONFERMA=1`: roles first, then `pg_restore --clean
   --if-exists`, then the partitions for the coming days and the map view.
   Running it twice is safe.
4. If the server runs the sensors network: `uv run limen sensore
   ripristina-ca --dove "$LIMEN_SENSORI_DIR"`, then `make sensori-ca-init`
   (it keeps the restored CA and rebuilds, signed by it, the broker and
   ingestor credentials, the ACL and the CRL, which are not in the backup),
   then `make sensori-up`.
5. `make up`: migrations newer than the backup are applied, the restricted
   roles get their passwords.
6. Wait for the data that refills by itself: the hourly sweep fills
   `latest_risk` within the hour; the ISPRA layers come back with `make
   static-data` / `limen geoserver-sync`, OSM with `make osm-data`.
7. Check: `uv run limen data-status`, `uv run limen jobs`, and the map.

## Database schema (highlights)

`aoi`, `grid_cells`, `cell_static_factors`, `iffi_landslides`,
`pai_hazard`, `landslide_events` (dated event catalogue),
`risk_assessments` and `model_runs` (partitioned by UTC day), `latest_risk`,
`training_samples` (ML feature store), `norm_stats`, `raster_refs`,
`app_cache`, `alert_dispatches`, `forecast_dispatches` (predictive alert
dedup), `fwi_state` (the FWI chain per weather node), `glofas_riferimento`
and `glofas_previsione`, `cell_insar_features` (EGMS), `spiegazioni_regione`
(regional narratives), `seismic_events`, `fire_perimeters`, sensor tables,
`schema_migrations`. All geometries in EPSG:4326; distances/areas computed
in EPSG:3035 (LAEA Europe). Immutable SQL migrations in
`src/limen/data/migrations/NNN_*.sql`.

---

## Testing and quality gates

```bash
make test                  # unit + integration (testcontainers)
make test-unit             # fast, no Docker
make check                 # lint + typecheck + test
make lint                  # ruff check
make format                # ruff format
make typecheck             # mypy --strict on src/ (run after `uv sync --all-groups`)
```

Gate before every commit: `ruff check` + `ruff format` clean,
`mypy --strict` clean, `pytest` green. On Apple Silicon the integration
tests automatically use `imresamu/postgis-arm64` (override with
`LIMEN_TEST_POSTGIS_IMAGE`); `LIMEN_TEST_DATABASE_URL` points them at an
existing PostGIS instead of starting a container.

---

## Status and roadmap

Recently completed:

- **Three hazards in production**: landslides, floods and wildfires, with a
  72-hour per-cell forecast recomputed four times a day on the latest weather
  runs (no longer once a night).
- **Italian and English**: the SPA, the regional narratives and the national
  picture are available in both languages.
- **Copernicus data at the source**: the GloFAS forecast and each river
  node's ordinary high flow from the EWDS, EGMS ground motion from the CLMS
  archive with a service key and a nightly check for new releases.
- **«Regions to watch» page** (`#/regioni`): regions ordered by estimated
  danger, now and over the next 72 hours, with the official alert alongside
  and a narrative per hazard written by Claude, with no invented numbers. The
  report downloads as **PDF** (`/api/regioni/rapporto.pdf`, also for a single
  region).
- **National picture driving the side column**: once a hazard is chosen, the
  «Most exposed comuni» list (`/api/comuni?hazard=`) and each comune's chart
  speak only of that hazard, with its own class cutoffs.
- **The first sweep after a restart** of the worker starts after two minutes,
  not an hour: the map no longer freezes at every deploy.
- **National coverage** (20 ISTAT regions) with the Caine threshold re-fitted
  on e-ITALICA.
- **No user authentication, by design** (epic #69). Limen is a public map
  dashboard: map, national picture, alerts, comuni and shadow-model
  diagnostics open without a login. The login that existed protected the
  *page*, not the data — every API feeding the dashboard was already public,
  so a `curl` got everything. Launching a sweep, the only privileged
  operation, stays on the CLI (`limen monitor-once`) and on MCP behind
  `MCP_ADMIN_TOKEN`, fail-closed. The database auth work (#49) remains in git
  history and can be recovered if an area for Regional or Civil Protection
  operators is ever needed.
- **Trained ML challenger** on 37k samples (e-ITALICA landslides +
  per-sample antecedent rainfall): **AUC-PR 0.60 vs 0.28 for the
  deterministic engine** on the same spatial partition and the same rainfall
  (`limen train`; MLflow registry; manual promotion only). Backup/restore of
  dataset and model: `make dump-training` / `make restore-training`. The
  nightly backup above covers them too.
- **Shadow mode active**: the ML challenger runs alongside the champion every
  night (`SCORING__MODE=shadow`) and writes its probabilities to
  `model_runs`; the deterministic engine stays the only authoritative one.
- **Shadow-ML diagnostics** (issue #26): `/api/shadow/summary` (agreement /
  divergence per region + real events), shared with the `limen shadow-report`
  CLI; a plain-language panel in the dashboard; and a public `#/diagnostica-ml`
  page with recall on real events, agreement per region and a per-cell
  **divergence map** (neutral palette, not the risk one). Non-authoritative —
  V1 always drives the alerts.
- **MCP `limen-ops`** (`limen mcp-serve`): risk, alerts and workflow runs
  exposed as tools for agent gateways (OpenClaw, Claude Desktop). In compose
  it is the `mcp` service (image `limen/api:0.1`, the api one, HTTP on `127.0.0.1:8766`;
  `LIMEN_MCP_BIND=0.0.0.0` only behind TLS when the gateway is on another
  machine). OpenClaw hook-up:
  `openclaw mcp set limen-ops '{"url":"http://127.0.0.1:8766/mcp","transport":"streamable-http"}'`.
- **`webhook` notification channel**: alerts POST the JSON payload to the
  agent gateway (e.g. OpenClaw `/hooks`, bearer token) — pull via MCP for
  questions, push via webhook for events. Config:
  `NOTIFICATIONS__ENABLED_CHANNELS=["webhook"]` + `NOTIFICATIONS__WEBHOOK__URL/TOKEN`.
- **«How it works» guide** in the frontend (`#/come-funziona`, one sub-route
  per section) with a simulator that uses the real production formula.
- **Event-driven pipeline** (on by default, opt-out `FORECAST__ENABLED=false`):
  a predictive sweep at `now+48h` with forecast rain; cells at level ≥
  `FORECAST__MIN_LEVEL` trigger a **predictive** alert on the same channels
  (webhook/OpenClaw, Telegram…), labelled "FORECAST", with a deterministic
  summary and (AOI, horizon) dedup separate from the operational alerts.
- **DPC radar nowcast** (on by default): the national radar network's 1 km
  SRI acts as a short-horizon trigger — intense rain seen by the radar ⇒
  immediate scoring of the affected region.
- **`llm-training/`**: an (assessment → briefing) dataset in Alpaca format +
  a step-by-step guide for an eventual fine-tuning with LLaMA-Factory.

Next steps:

- **The rainfall signal for landslides** (#122): scale is not the lever (see
  «Where we honestly stand»). We are looking at the rainfall component in the
  missed cells — hourly intensity against accumulation, the 48-hour window,
  Caine thresholds per macro-region — always tuning on one group of regions
  and checking on the others before touching the production engine.
- **Shadow verdict** of the ML challenger against the deterministic engine
  (`uv run limen shadow-report`); promotion **manual** only.
- **Reliability plot** for the ML diagnostics, once there are enough real
  events (#30).

---

## Attribution and open licences

Limen uses the following open datasets — attribution is mandatory when the
map / briefings are published:

* **ISPRA IdroGEO** (IFFI inventory, PAI landslide and hydraulic mosaics) —
  © ISPRA / Italian authorities, CC-BY 4.0. https://idrogeo.isprambiente.it
* **e-ITALICA** (rainfall-triggered landslide catalogue, CNR-IRPI) —
  CC-BY 4.0, Zenodo DOI 10.5281/zenodo.14204473.
* **Copernicus** (Open-Meteo, ERA5, **CERRA** regional reanalysis) —
  Copernicus licence, free use with attribution. https://open-meteo.com
* **Copernicus EMS — GloFAS** (river discharge, via Open-Meteo and from the
  Early Warning Data Store) — CEMS-Floods licence: free use, but whoever
  publishes derived data must state «Contains modified Copernicus Emergency
  Management Service information [year]» and must not present it as a flood
  warning. Limen does so on the map (flood and overview), in the home footer,
  in the flood articles of «Verifiche» and in the regions PDF
  (`frontend/src/lib/attribuzioni.ts`, `report/regioni_pdf.py`). Data
  restricted by art. 12 of Reg. (EU) 1159/2013 (real-time EFAS) must not be
  republished. https://ewds.climate.copernicus.eu
* **Copernicus EMS — CEMS Fire** (fire danger indices on ERA5,
  `cems-fire-historical-v1`) — CC-BY 4.0. https://ewds.climate.copernicus.eu
* **Copernicus Land — EGMS** (European Ground Motion Service, Ortho L3
  product: mean ground velocity at 100 m from Sentinel-1, vertical and
  east-west components) — Copernicus Land open licence (Reg. EU 2021/696):
  free use citing «Generated using European Union's Copernicus Land
  Monitoring Service information» and stating the modifications. Download
  requires a CLMS service key (`EGMS__SERVICE_KEY`, profile on
  land.copernicus.eu → «API Tokens»). Today it feeds only the ML features,
  not the map. https://egms.land.copernicus.eu
* **INGV** (FDSN event service, ShakeMap) — CC-BY 4.0.
  https://terremoti.ingv.it
* **EFFIS** (burnt-area perimeters) — Copernicus EFFIS terms.
* **NASA FIRMS** (active VIIRS/MODIS hotspots, NRT + per-country archive
  since 2000) — NASA data, free use with attribution; the per-country
  archive needs no credentials. https://firms.modaps.eosdis.nasa.gov
* **Copernicus EMS Rapid Mapping** (observed flooded perimeters, the flood
  backtest truth set) — © European Union, Copernicus EMS: free with
  attribution, no credentials. https://rapidmapping.emergency.copernicus.eu
* **DPC radar platform** (SRI and «Merging» accumulations) — CC-BY-SA.
* **CORINE Land Cover 2018 Italy** (SINAnet/ISPRA) — CC-BY.
  https://groupware.sinanet.isprambiente.it
* **Geolithological Map of Italy 1:500k** (PCN/MASE National Geoportal,
  Geological Survey of Italy) — CC-BY 4.0.
* **ISTAT** (2023 administrative boundaries) — CC-BY 4.0.
* **OpenStreetMap** (basemap) — ODbL.

---

## Support Limen

Limen is developed and hosted by [Agent Engineering Studio](https://www.agentengineering.it)
on its own server, with no advertising and no collection of personal data.
Autumn brings the rains, and the rains bring landslides and floods: that is
when an open map of the danger is most useful.

* ⭐ **Star** the repository: it is the simplest way to help people working
  on civil protection, geology and open data find it.
* ☕ **Buy us a coffee** on [Buy Me a Coffee](https://www.buymeacoffee.com/f9t3zol)
  (or with the *Sponsor* button at the top): it covers the server, the
  weather archives and the time to tune the engine on real data.

  <a href="https://www.buymeacoffee.com/f9t3zol"><img src="https://img.buymeacoffee.com/button-api/?text=Buy%20me%20a%20coffee&emoji=&slug=f9t3zol&button_colour=FFDD00&font_colour=000000&font_family=Cookie&outline_colour=000000&coffee_colour=ffffff" alt="Buy me a coffee" height="40"></a>
* 🏛️ **Public bodies, municipalities, universities**: for trials on your
  territory, write to us from [agentengineering.it](https://www.agentengineering.it).
* 🔁 **Share** the [live map](https://limen.agentengineering.it/) and tell
  us, with an issue, where the estimated danger does not look right to you.

## How it was built

Limen has been developed with [Claude Code](https://claude.com/claude-code)
since its first commit, on 3 June 2026: most commits are written together
with Claude, as the `Co-Authored-By` line of each one says. The regional
narratives are written with Claude, Anthropic's model, and change no number.
Limen is an independent project, not affiliated with Anthropic.

## Contributing and governance

* [`CONTRIBUTING.md`](./CONTRIBUTING.md) — dev setup, commit style, gates.
* [`SECURITY.md`](./SECURITY.md) — private disclosure channel; the threat
  model in [`.oss-scanner/threat_model.md`](./.oss-scanner/threat_model.md)
  says where untrusted input enters and how we rate severity.
* [`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md) — community code of conduct.
* [`ROADMAP.md`](./ROADMAP.md) — direction and next steps.
* [`docs/OSS_IMPACT.md`](./docs/OSS_IMPACT.md) — open-source impact and reusable components.
* [`CHANGELOG.md`](./CHANGELOG.md) — versioned history (Keep a Changelog).

> Limen is a **decision-support** tool: its outputs are modelled indicators,
> not official Civil Protection alerts.

## Licence

Copyright © 2026 Giuseppe Zileni. Limen is a personal project, developed
outside any employment relationship and with the author's own means: the
rights holder is the author, who is also the party to whom the CLA grants
the licences.

[EUPL-1.2](./LICENSE) — European Union Public Licence, copyleft that also
covers use over a network: whoever offers Limen as a service must publish
their modifications. Versions up to `v0.6.0-impl-complete` remain
Apache-2.0.

A commercial licence is available for uses incompatible with copyleft:
write to the maintainer. External contributions require the CLA described in
[CONTRIBUTING.md](./CONTRIBUTING.md#contributor-license-agreement).
