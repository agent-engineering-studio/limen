# Changelog

All notable changes to Limen are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.0-geodata] — 2026-06-04 — Geo-Data Service + ispra-geo MCP (Phase 12)

Phase 12 — adds the **opt-in** `geodata` compose profile per
§3.3.4-ter. Dedicated VPS-only stack that downloads heavy ISPRA
datasets into its own PostGIS volume and serves them three ways:
per-cell features for the operational DB (Neon stays light), PMTiles
for the map (zero DB load at view time), and an `ispra-geo` MCP
server for agents (read-only + admin-guarded refresh). Never on
Neon, never in the hourly critical path.

### Added

* New top-level workspace member `geodata/` (`limen-geodata` 0.1.0)
  — self-contained Python package, designed to be extractable into
  a standalone repo with a one-directory move (`from geodata.* import`
  never depends on `limen.*`).
* `geodata.manifest` — Pydantic v2 schema that refuses any URL
  outside `https://idrogeo.isprambiente.it/` by construction, plus
  the shipped `datasets.yaml` covering the national PAI mosaic,
  per-region IFFI ZIPs (Puglia + Basilicata × line/poly/aree/dgpv),
  the IFFI Dizionari JSONs, and the disabled flood `idraulica` entry.
* `geodata.init` — streaming downloader (httpx + tenacity, retries
  5xx/429/transport, no full file in memory), `safe_unzip` (refuses
  path-traversal + absolute paths + symlinks), format-specific
  pyogrio importers (PAI / IFFI shapefiles + Dizionari JSONs), and
  a runner with `--only` / `--region` / `--force` / `--dry-run`.
  Per-dataset failures never abort the others.
* `geodata.db` — own PostGIS DDL (`dataset_versions`,
  `pai_landslide_hazard`, `idraulica_hazard`, `iffi_landslides`,
  `iffi_lookup_*`) + idempotent schema bootstrap + skip-if-unchanged
  checksum lookup.
* `geodata.exports.features` — `limen geodata export-features --to
  <dsn>` upserts `pai_class_norm` + `iffi_density_500` +
  `distance_to_iffi_m` into the operational `cell_static_factors`.
  Only numeric columns cross the wire; Neon stays light.
* `geodata.exports.pmtiles` — `limen geodata make-pmtiles` streams
  GeoJSON FeatureCollections (asyncpg cursor with prefetch) and
  shells out to `tippecanoe` for `.pmtiles` per layer.
* `geodata.mcp` — `ispra-geo` FastMCP server with five tools:
  `hazard_at`, `iffi_query` (decodes `movement_type` via the
  Dizionario), `pai_summary` (km² area via geodesic), `dataset_status`,
  and admin-token-guarded `refresh`. `stdio` + `http` transports.
* `limen geodata` nested CLI dispatcher (`list / init / export-features
  / make-pmtiles / mcp`). Lazy-imports `geodata.*` so the main CLI
  doesn't pull pyogrio / fastmcp.
* `geodata/Dockerfile` — small image (no data baked in) carrying
  Python + GDAL/PROJ + tippecanoe.
* `infra/docker/docker-compose.geodata.yml` — `geodata` profile with
  `geodata-db` (port 55432), `geodata-init` (one-shot), `ispra-geo-mcp`
  (HTTP 8765). Resource limits + healthchecks + opt-in profile.
* `geodata/claude_desktop_config.example.json` — drop-in Claude
  Desktop entry pointing at `limen geodata mcp --transport stdio`.
* `docs/geodata.md` — full operator guide.

### Tests

* +72 unit: manifest schema (unofficial-URL refusal, duplicate-name
  guard, region filter, name pattern), parser aliasing + PAI class
  normalisation + defensive shape, downloader streaming + 5xx retry
  + safe-unzip path-traversal / absolute-path / directory entries,
  runner filter (only / region / combined / dry-run / no-target),
  export feature aggregation (PAI ladder monotonicity, most-severe
  selector, IFFI density saturation, GeoJSON feature serialisation),
  MCP tools (lat/lon range, lon/lat ordering, region normalisation,
  Dizionario JOIN, SQL shape, admin-token gate truth table, refresh
  permission errors). 279 unit total green; mypy --strict clean;
  ruff clean.

## [0.4.0-v2.x] — 2026-06-04 — KG grounding (V2.x)

Phase 11 — adds the **advisory** knowledge-graph grounding layer. The
deterministic V1 engine and the V2 ML champion's numeric outputs are
NEVER affected; this layer only enriches the Italian briefing with
citations drawn from the team's `knowledge-graph` sidecar.

### Added

* `KgSettings` — off by default. Knobs: `enabled`, `base_url`,
  `thread_id` (default `landslide-kb`), `timeout_seconds` (default 3s),
  `cache_ttl_seconds`, optional bearer token, `top_k`.
* `limen.knowledge.ontology` — landslide-domain ontology (§2.8):
  Paper / Author / RainfallThreshold / TriggerMechanism / LandslideType
  / Lithology / Region / Area / HistoricalEvent / NormativePlan and the
  six relations (DEFINES_THRESHOLD / VALID_FOR_REGION / TRIGGERED_BY /
  DOCUMENTED_IN / OCCURRED_IN / SUPPORTS_PARAMETER). Versioned bundle
  shipped to the sidecar at ingest time.
* `limen.knowledge.schema` — narrow Pydantic v2 payloads for
  `POST /ingest` (`IngestDocument`, `IngestRequest`) and `POST /query`
  (`GroundingQuery`, `Passage`, `GroundingResult`). `extra=forbid` so
  sidecar API drift surfaces as a validation error, not silent breakage.
* `limen.knowledge.ingest` + `limen ingest-kb` CLI — offline-batch
  loader walking a corpus directory (suffix-to-kind mapping for paper /
  PAI / ISPRA / IFFI event / past briefings), idempotent via the
  sidecar's natural-key dedup + Limen's `dataset_versions` content hash.
* `limen.agents.grounding.kg_client.KgClient` — REST wrapper over
  `POST /query`; every failure path returns an empty result.
* `limen.agents.grounding.service.GroundingService` —
  `(region, mechanism)` cache layer over `app_cache`. Different
  `top_k` requests reuse the same cached set sliced client-side.
  Empty results are cached so an un-ingested sidecar doesn't generate
  repeat traffic.
* `limen.agents.grounding.format.format_citations` — deterministic
  Markdown citation block in Italian appended *after* the 250-word
  narrative (citations sit outside the word count).
* `BriefingAgent` accepts an optional `grounding: GroundingService`:
  launches the KG task **concurrently** with the LLM call so total
  latency stays at `max(LLM, kg.timeout_seconds)`; cancels the task
  on any LLM failure; splices citations onto every success / trim /
  retry return path.
* `WorkflowDeps.grounding_service` + `AppDependencies.grounding_service`
  + lifespan wiring — KG service is built only when `kg.enabled`.
* `infra/docker/docker-compose.demo.yml` — new `kg` profile + LLM
  provider coherence env-threading (§3.7).
* `docs/grounding.md` + `.env.example` `KG__*` block.

### Tests

* +20 unit (KG client happy-path / 5xx / timeout / decode error / top_k
  cap / query payload shape; service cache key stability across top_k
  and case-insensitive region; cache hit on second identical query;
  empty result cached; different mechanism misses separately; briefing
  without grounding has no citations; briefing with grounding up has
  citations; KG timeout doesn't leak into critical path (<1s); KG
  disabled bypasses entirely; briefing without analysis skips KG; KG
  failure during LLM-fail path doesn't block fallback).

## [0.3.0-v2] — 2026-06-04 — ML engine & MLOps (V2)

Phase 10 — adds the V2 ML engine, training pipeline, EGMS InSAR
features, DL sub-model, and drift monitoring **alongside** V1. The
deterministic engine remains the champion until a ML challenger
beats the V1 baseline on spatial-block CV + the §2.5 backtest.

### Added

* `ScoringEngine` Protocol — V1 + V2 share the same bundle→RiskScore
  surface (runtime-checkable). Engine selected via
  `SCORING__ENGINE=deterministic|ml`; failures fall back to V1.
* `SCORING__MODE=champion_only|shadow` champion-challenger toggle.
  `ShadowChallengerExecutor` runs the other engine in parallel, writes
  predictions to `model_runs`, and **never** mutates `cell_results`.
* Migration `010_ml_tables.sql` — `training_samples` (point-in-time
  correct features + `split_block` for spatial-block CV),
  `cell_insar_features` (EGMS aggregates), `model_runs` (challenger
  predictions).
* `limen.ml.feature_store` — IFFI-positive + balanced background
  sampler, coarse spatial-block grid, deterministic round-robin
  CV partition (no leakage by construction).
* `limen.ml.train` (`limen train`) — Optuna TPE over LightGBM hyperparams
  (objective = AUC-PR), spatial-block CV, isotonic calibration on
  out-of-fold predictions, SHAP TreeExplainer, full MLflow tracking
  + Model Registry registration. Promotion gate enforces auc_pr_min /
  brier_max / hit_rate_min / far_max / lead_time_hours_min AND requires
  the ML AUC-PR to beat the V1 baseline AUC-PR on the same partition.
* `limen.core.scoring.ml_engine.MLScoringEngine` — drop-in V2 engine
  loaded from MLflow.
* `limen.integrations.egms` (`limen sync-egms`) — Copernicus EGMS
  scatterer fetch + per-cell aggregation into `cell_insar_features`.
* `limen.ml.dl` — 1D-CNN over a 1-week hourly rainfall window, trained
  offline (PyTorch) and served via ONNX runtime.
* `limen.ml.monitoring` — PSI, KS, prediction drift, RetrainingTrigger.
  APScheduler job `limen-drift-monitor` (gated by
  `MONITORING__ENABLE_DRIFT_MONITORING`).
* Optional dependency groups: `ml` (lightgbm, mlflow, optuna, shap,
  scikit-learn, onnxruntime, numpy, pandas) and `dl` (torch, onnx).
* `docs/ml.md` — pipeline + promotion gate + champion-challenger +
  storage.

### Tests

* +35 unit tests across Stages A–F: Protocol satisfaction + resolver
  fallback, spatial-block CV correctness + balance, dataset packing,
  promotion-gate truth table, shadow-executor cell_results invariance
  and persistence-failure suppression, EGMS aggregation (median
  robustness, period envelopes, point→cell join), DL pad/trim and
  neutral fallback, PSI/KS/prediction-drift correctness +
  RetrainingTrigger fan-out.

## [0.2.0-v1.5] — 2026-06-04 — In-situ IoT (V1.5)

Adds a hybrid MQTT + SensorThings ingestion path and a new kinematic
component K so the deterministic engine can consume directly-measured
rainfall / pore pressure / soil moisture / displacement on
sensored cells. Gated by `enable_insitu`; with it off the system is
byte-for-byte the V1 behaviour (`test_invariance_no_sensors_matches_v1`
proves this).

### Added

* Migration `009_sensor_tables.sql` — `sensor_devices`, the
  partitioned `sensor_observations`, `sensor_features_hourly`, and the
  `ensure_sensor_partition_for_month()` helper.
* `limen.integrations.iot` — SensorThings-aligned `Observation`
  schema, `run_qc()` pipeline (range / spike / flatline / gap / unit),
  partition rollover helper, `MqttIngestor` (`aiomqtt` subscriber on
  `limen/v1/+/+/+/+/obs` with the LWT pattern), and `run_hourly_rollup`.
* Three sensor repos: `sensor_devices_repo`, `sensor_observations_repo`,
  `sensor_features_hourly_repo`.
* `compute_kinematic()` + the engine's regime renormalization
  (`w_K + (1 - w_K) * pure_V1_sum`).
* Measured-over-modeled override on M (Caine, API, soil) with the
  overridden inputs recorded on `MeteoBreakdown.measured_overrides`.
* Hard-escalation flag on `RiskScore` and `CellRiskRecord` — set by
  the engine on acceleration / inverse-velocity alarm, propagated
  through `EscalationGateExecutor`, and consumed by
  `AlertDispatchExecutor` to bypass the `min_level` threshold.
* Two new APScheduler jobs (gated by `enable_insitu`):
  `limen-iot-rollup` (every `iot.rollup_minutes`) and
  `limen-iot-partition-rollover` (monthly).
* `IotSettings` env block + a YAML `kinematic:` block (optional —
  older YAMLs without it still validate, with K stuck at 0).
* `docs/iot.md` — pipeline + storage + QC + configuration overview.

### Changed

* `SensorFetchExecutor` now reads `sensor_features_hourly` for real
  (V1 was a logging stub).
* The risk endpoint normalises `measured_overrides` back to a tuple
  when reading persisted assessments.

### Tests

* +33 unit tests covering schemas, QC, ingestor handler pipeline,
  kinematic monotonicity, hard-escalation, measured override, and the
  V1=V1.5(disabled) invariance.
* +2 integration tests (repos + rollup) against the testcontainers
  Postgres+PostGIS.

## [0.1.0] — 2026-06-04 — V1 prototype

The complete V1 prototype: data layer + integrations + scoring + MAF
workflow + FastAPI host + interactive map + multi-channel
notifications, plus Phase 8 polish (CI/CD, observability dashboards,
documentation, demo).

### Added

* **Phase 0–1** — uv project scaffold, asyncpg + PostGIS data layer
  with the idempotent migration runner, `ObjectStore` Protocol
  (filesystem + S3-compatible), Postgres-backed cache, AOI + 1 km
  grid for Puglia + Basilicata. (`limen seed`, `limen migrate`.)
* **Phase 2** — Open-Meteo (forecast + ERA5), ISPRA IdroGEO (IFFI +
  PAI + susceptibility), INGV (FDSN events + ShakeMap raster), EFFIS
  (burnt-area perimeters) clients with shared tenacity retry + graceful
  degradation. Static-feature bootstrap CLI
  (`limen bootstrap-static`).
* **Phase 3** — V1 deterministic scoring engine: Caine I/D excess,
  API Kohler-Linsley, seismic exponential decay, post-fire window,
  weighted linear combination + 5-class classifier. YAML-driven via
  `regional_thresholds.yaml`. `limen calibrate` runs the
  §2.5 S↔ISPRA correlation gate; `limen backtest` produces the
  hit-rate / FAR / lead-time report.
* **Phase 4** — MAF-shaped workflow with 10 custom executors,
  RiskAnalyst (strict JSON output) and Briefing (150–250 Italian
  words) ChatAgents, LLM factory + resolver (Anthropic > OpenAI >
  Foundry > Ollama). `limen monitor-once`.
* **Phase 5** — FastAPI host with typed dependency injection,
  APScheduler hourly / weekly / cache-cleanup jobs, OpenTelemetry
  tracing instrumentors + five custom metric instruments, multi-stage
  uvicorn Docker image (`limen serve`).
* **Phase 6** — `mv_latest_risk` matview + `refresh_mv_latest_risk()`
  helper; pg_tileserv tile server; Vite + React + MapLibre public map
  with `RiskMap`, `LegendPanel`, `AlertList`, `CellPopup`,
  `TimelineSlider`.
* **Phase 7** — `NotificationDispatcher` with three channels
  (Telegram via httpx, MQTT via aiomqtt, Email via aiosmtplib),
  dedup window, exposure-weighted priority, real
  `AlertDispatchExecutor` replacing the V1 logging stub.
* **Phase 8** — CI/CD (backend + frontend + Docker image build +
  GHCR push), deploy stubs for Aruba SSH and Azure Container Apps,
  Grafana LGTM observability stack with provisioned dashboards
  ("risk metrics" + "system health"), bilingual quickstart README,
  docs split across `architecture.md`, `data-model.md`,
  `scoring-model.md`, `api.md`, `runbook.md`, `deployment.md`,
  `CONTRIBUTING.md`, `SECURITY.md`.

### Engineering

* `mypy --strict` clean across the full backend.
* `ruff check` + `ruff format --check` clean.
* Backend coverage ≥ 80% (gate enforced in pyproject + CI).
* Frontend strict TypeScript + ESLint + Vitest + Vite build green.
* Conventional Commits throughout.

### Engine-agnostic guarantees

* Same code on local Docker Postgres+PostGIS, Neon dev/test branches,
  Aruba VPS production — only `DB__CONNECTION_STRING`,
  `OBJECT_STORE__*` and LLM keys change.
* APScheduler in-process so periodic jobs work even when `pg_cron` is
  unavailable (Neon).
* The deterministic scoring engine remains a pure function; the LLM
  agents only reformulate the numeric breakdown.

### Documented future work

* **V1.5** — IoT in-situ sensor ingestion + component K (the
  `SensorFetchExecutor` is already a wired no-op stub).
* **V2** — ML scoring engine drop-in replacement consuming the same
  `CellFeatureBundle`.
* **V2.x** — Knowledge-graph grounding of the Italian briefing.
* **Authentication** — Clerk via `@clerk/clerk-react` on the same Vite
  SPA + JWT validation in FastAPI (deferred per project doc §1.6).
* DEM / CORINE / ISPRA Carta Geologica ingest pipeline to fill the
  currently-NULL columns on `cell_static_factors`.

[Unreleased]: https://github.com/agent-engineering-studio/limen/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/agent-engineering-studio/limen/releases/tag/v0.1.0
