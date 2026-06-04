# Changelog

All notable changes to Limen are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
