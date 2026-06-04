# Changelog

All notable changes to Limen are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
