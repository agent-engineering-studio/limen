# Limen — Claude Code project guide

> 🔴 **NUOVA MACCHINA / NUOVA SESSIONE: leggi prima [`docs/HANDOFF.md`](./docs/HANDOFF.md)**
> — stato corrente, cosa correggere dopo la migrazione su server dedicato
> (path assoluti in `.env`, Docker/PostGIS x86), lavoro in sospeso, e il
> contenuto delle memorie locali di Claude (che NON si trasferiscono col repo).

> AI multi-factor landslide-risk monitoring for the Italian territory.
> Pilot: **Puglia + Basilicata**. Current state: **implementation
> complete (0.6.0-impl-complete) — entering formal testing**.
> V1 prototype (Phases 0–8) + V1.5 in-situ IoT (Phase 9) + V2 ML
> stack (Phase 10) + KG grounding (Phase 11) + Geo-Data Service
> (Phase 12) + Flood / DEM / CORINE / Geological / SHAP-backed ML
> component breakdown / EFFIS bulk fallback / official ISTAT seed
> AOIs / static PMTiles overlays. Every scoring component
> (S/M/E/F/H/K) has at least one tested opt-in data-feed pipeline;
> the deterministic V1 engine remains the production champion.
> Next session opens the formal test cycle. See `README.md`,
> `docs/ml.md`, `docs/grounding.md`, `docs/geodata.md`.

---

## Deployment context (mandatory)

- **Target**: self-hosted VPS + Docker containers. **No cloud providers** — no
  AWS, no Azure, no GCP. Stored in memory as `deploy-target`.
- **Database**: PostgreSQL 16 + PostGIS, containerised in production.
  **Neon** is allowed only for dev/test branches.
- **Object storage**: `filesystem` (volume mount) or `s3`-compatible
  (MinIO sidecar, R2, B2 — via
  `OBJECT_STORE__ENDPOINT_URL`). Never AWS SDK calls. Never Azure Blob.

---

## Locked invariants (never violate)

| Topic | Rule |
|-------|------|
| Language | Python 3.12+, `uv` for everything (`uv sync`, `uv run`). |
| Layout | `src/limen/...`, package = `limen`. Tests in `tests/`. |
| License | **EUPL-1.2** dal 2026-10-11 (fino a `v0.6.0-impl-complete` il codice era Apache-2.0, e quelle versioni restano tali). Contributi esterni solo con il CLA di `CONTRIBUTING.md`: è ciò che tiene aperta la doppia licenza. |
| DB access | `asyncpg` + the PostGIS hex-EWKB codec in `limen.data.db`. **No ORM.** |
| Migrations | Plain SQL in `src/limen/data/migrations/NNN_*.sql`, applied by `limen.data.migrate`. Tracked with SHA-256 checksums. **NEVER edit an applied migration** — add a new file. Comments count: even a comment-only change breaks the checksum. |
| Object store | Use the `ObjectStore` Protocol only. Never `import boto3` in app code. The factory in `limen.data.object_store.factory` is the only place that picks a backend. |
| Settings | `pydantic-settings` with `env_nested_delimiter="__"`. New env vars go through `limen.config.settings.Settings`. |
| LLM | Resolver order: Anthropic → OpenAI → Foundry → **llama.cpp**. A cloud key wins over the local engine unless `LLM__PROVIDER` overrides. Default engine is the self-hosted **llama.cpp/llama-swap** server; Claude is opt-in via `ANTHROPIC_API_KEY`. Ollama needs `LLM__PROVIDER=ollama`. |
| Scheduling | `pg_cron` is optional. The same job must work via APScheduler when pg_cron is absent (Neon). |
| Logging | `structlog.get_logger(__name__)` via `limen.core.logging.get_logger`. **Never `print`.** |
| Geometry CRS | All geometries stored in EPSG:4326. Compute distances/areas in EPSG:3035 (LAEA Europe). |
| Quality gates | `ruff check` + `ruff format` clean, `mypy --strict` clean, `pytest` green before commit. **The gate is `make check`** (lint + typecheck + `pytest --cov=limen`, coverage ≥ 80 %); in CI it is split so a slow suite cannot hide a lint failure (#90): `backend` runs lint + types + `tests/unit` as the fast gate on every PR, `integration` runs the whole suite with the coverage threshold, and `slow` runs the national-seed tests on `main` only. Tests marked `slow` are **deselected by default** (`addopts` carries `-m 'not slow'`) — run them with `make test-slow`. An integration test that needs an AOI seeds **one** with `run_seed(only=[SEED_SMALL_AOI])`: seeding the twenty regions is ~312,000 cells and twenty minutes, and it is what kept the CI red from July to September without a single test actually failing. |
| External HTTP | All outbound calls go through `limen.integrations._http` (shared `httpx.AsyncClient` + tenacity policy: 4 attempts, exp backoff cap 60 s, retries on transport errors + 5xx/429). |
| Degradation | Read-only operations that miss external sources return a *neutral result* (`None`, `[]`, `{}`) and log `integration.degraded` — they MUST NOT raise. Writes do raise. |
| Il bootstrap statico è idempotente sul **costo** | `bootstrap_static_for_aoi` salta ogni passo la cui sorgente non è cambiata (#101). L'impronta sta in `integrations/static_bootstrap/fingerprint.py` e tiene tre cose: la **sorgente** (mtime+dimensione per i file, conteggio+ultimo inserimento per le tabelle — mai l'hash del contenuto, che su un mosaico DTM costa quanto ricalcolare), il **numero di celle dell'AOI** (un re-seed che cambia la griglia invalida tutto: i fattori sono per cella) e una **versione di codice per passo** (`STEP_VERSION`, da bumpare quando cambia la *formula* e non il dato — è successo con il WUI della #62 e con `imperviousness_norm` della #63). La chiave è `(aoi_id, passo)`: aggiungere una regione ne calcola una, non rifà le altre diciannove. Una sorgente non configurata resta uno `static_bootstrap.skip`, mai un errore. `make up`, `make init` e `make static-data` passano tutti da `scripts/load_static_data.sh`: **non aggiungere una quarta variante**. |
| Idempotency (sync jobs) | Compute SHA-256 over canonical-JSON of the fetched payloads, look up `dataset_versions(source, dataset, version)`. If the version exists, **skip all writes**. |
| Scoring engine purity | `MultiFactorScoringEngine.score(bundle) -> RiskScore[ComponentBreakdown]` is a *pure* function: no DB, no network, no LLM. Assembling the bundle is a separate concern. |
| Magic numbers | All weights, thresholds, sigmoid/decay params, and class cutoffs live in `src/limen/config/hazards/<hazard>.yaml`. Each hazard has its **own schema** (`SCHEMA_BY_HAZARD`): `RegionalThresholds` for landslide, `WildfireThresholds` for wildfire, sharing only `HazardThresholds` (version, class cutoffs, PC mapping, exposure). There are **no hard-coded constants** in scoring code — tests prove it via YAML override. The exception is Van Wagner's FWI coefficients: they are a published standard, not a calibration, so they live in `wildfire/fwi.py` and the YAML carries only what a deployment may choose. |
| LLM precedence | `LLM__PROVIDER` override > `ANTHROPIC_API_KEY` > `OPENAI_API_KEY` > Foundry creds > **llama.cpp**. Resolver: `limen.agents.llm_factory.resolve_llm_factory`. A cloud key always wins over the local engine unless explicitly overridden. The fallback moved from Ollama to llama.cpp: deployments relying on the implicit Ollama fallback must now declare `LLM__PROVIDER=ollama`. |
| LLM is non-authoritative | ChatAgents (RiskAnalyst, Briefing) only *reformulate* the deterministic scoring engine's numeric output. **Never** alter `score` / `breakdown`. An invariance test (`test_llm_does_not_change_numeric_breakdown`) enforces this. |
| Prompts are per hazard, and no prompt means no prose | The Italian prompts are written for a specific danger — the briefing one opens with *"spiega il rischio frane"*, and the RiskAnalyst schema's `driver` enum lists only slope-failure causes. `has_narrative(hazard)` in `chat_agents/prompts_registry.py` gates both LLM nodes: a hazard without a prompt ships **without narrative**, because a landslide persona narrating a fire is worse than silence. Adding one is a file drop (`<agent>.<hazard>.it.md`) plus, for RiskAnalyst, extending the `driver` enum. Flood and wildfire have theirs since #155, and the agents now pick the prompt from `assessment.hazard_type` (before, they loaded the landslide one whatever the hazard). The async briefing re-narrates a region only when its dominant class changed or after `LLM__BRIEFING_MIN_HOURS` (24 — at 12, fourteen rewrites out of eighteen came from the timer, not from a class change): every hourly sweep is a new run, and with three hazards on a paid model that was up to 1,440 briefings a day. Both narrative roles run on `fast-cloud` (Claude Haiku 5.5, ~1–3 $/month); every response logs `llm.usage` with its tokens. |
| Agents prompts in `*.it.md` | Prompt files live next to the agent in `src/limen/agents/chat_agents/prompts/`. Loaded with `importlib.resources`. Never inline a long prompt in Python source. |
| API has no business logic | Endpoints under `src/limen/api/endpoints/` only call the Phase-4 workflow or the Phase-1 repos. New behaviour goes in `agents/` or `core/`, never in route handlers. |
| DI not globals | Everything routes need is in `AppDependencies` injected via FastAPI `Depends()`. No `from limen.x import _GLOBAL_THING` inside endpoints. |
| Three cadences, not thirteen schedules (#78) | **Hourly** (`profile="hourly"`): V1 only — persistence and alerts, no LLM, no shadow. It is the path that must fit inside the tick, and the measurement says why: on 10,353 cells the two narrative nodes cost 140.3 s of a 156 s sweep against 0.88 s of actual scoring. The radar-nowcast and FIRMS triggers use the same profile. **Asynchronous** (`briefing_enrichment`, every `LLM__BRIEFING_INTERVAL_MINUTES`): the narrative for escalated AOIs, one at a time, written to `spiegazioni_regione` (migration 064), one row per (region, hazard) — never onto `risk_assessments`/`latest_risk`. It used to be attached to the sweep's rows, and both halves broke: the selective write (#135) leaves a quiet sweep with no rows ("no rows" on every region), and the sweep rewrites `latest_risk` every hour, wiping the text. The summary is built from `latest_risk` (`summary_for_region`); a text that is the deterministic fallback is stored with `ripiego = true` and the SPA does not attribute it to the AI. **Nightly** (`limen-nightly` at `SCHEDULER__NIGHTLY_HOUR_UTC`): shadow ML, drift, retrain, partitions, retention — in that order, each a `job_runs` row, a failing step never stopping the next. The **per-cell forecast** (`limen-forecast-history`) left the night: it runs at `SCHEDULER__FORECAST_CELLS_HOURS_UTC` (02/08/14/20 :20), because computed once at 02:00 it stayed on the map for 24 hours — on 7 October 2026 it showed Basilicata «molto alto» for Saturday's wildfire on the night's weather, while the morning runs brought rain and 84 % humidity and the same chain gave zero. `profile="nightly"` neither persists nor alerts: the night measures, it does not operate. The standalone schedules for drift, forecast history and cache cleanup are gone — reintroducing one makes it run twice. |
| APScheduler not pg_cron, **in the `worker` process** | Periodic jobs (hourly monitoring, weekly ISPRA sync, cache cleanup when configured) run via APScheduler so the same code works on Neon — but in the **`limen worker`** process, not the API (#77). `SCHEDULER__ENABLED=false` in the `api` container: one event loop cannot serve a public map and grind 312k cells at the same time, and `risk_scoring.py` still carries the comment from when it tried. The worker runs at **one replica**, fixed in the compose: `_sweep_lock` is an in-process lock, so two replicas would mean two concurrent sweeps. The fix is that line, not a distributed lock. |
| Frontend = Vite (no Next.js), and **no user auth** | Phase 6 ships a public read-only map. Vite + React + MapLibre is the right surface; Next.js adds an unneeded Node server / RSC overhead. There is **no authentication** (epic #69): the whole SPA — map, national strip, alerts, comuni, shadow diagnostics — opens without a login, because the APIs feeding it were always public and a login protected the page, not the data. The one privileged action, launching a sweep, lives on the CLI (`limen monitor-once`) and on MCP behind `MCP_ADMIN_TOKEN`. Do not reintroduce a login for a hypothetical operator area — that is the future-proofing this file forbids; #49's work is recoverable from git if the need becomes real. |
| Tile pipeline | `mv_latest_risk` materialised view: `grid_cells` CROSS JOIN the enabled rows of `hazards`, LEFT JOIN the latest `risk_assessments` per **(cell, hazard)**. **Always refresh via `refresh_mv_latest_risk()`** (PersistResult executor calls it; it debounces to one refresh per 5 min and chains the comune rollup). Never `REFRESH MATERIALIZED VIEW mv_latest_risk` directly. |
| Engine registry is 2-D | Engines are registered per **(hazard, implementation)** in `core/scoring/registry.py` — hazard and implementation are orthogonal axes, so `(wildfire, ml)` has a home. Registering a factory plus adding `config/hazards/<hazard>.yaml` and its schema is the **only** production change a new hazard needs. Each factory narrows the base `HazardThresholds` to its own schema and raises on a mismatch. `resolver.py` stays the operational layer: it reads `SCORING__ENGINE` and degrades to the V1 baseline on any V2 failure, never raising. |
| Breakdown is per hazard | `RiskScore` is generic over a `HazardBreakdown` subclass, with a **covariant** TypeVar so `RiskScore[ComponentBreakdown]` is usable as `RiskScore[HazardBreakdown]`. `ScoringEngine` is `Protocol[BreakdownT_co]`: read the numbers ⇒ ask for the concrete breakdown, only serialise ⇒ ask for the base. PEP 695 syntax is **not** usable here (it infers the parameter as invariant and breaks that assignment) — UP046 is suppressed on the class with the reason next to it. |
| Consumers read breakdowns through projections | `CellRiskRecord` carries `breakdown: AnyHazardBreakdown`, never flattened components. Anything that must work for any hazard asks the breakdown: `components()` (named drivers, for narrative and escalation), `factors_payload()` (what goes into `risk_assessments.factors` — landslide's is byte-identical to the pre-Fase-2 shape, so stored rows and the breakdown endpoint are untouched), `predisposition()` (static susceptibility, for the below-High alert gate) and `measured()` (did the dynamic input actually arrive). Adding a hazard touches none of them. |
| «Non misurato» non è «nessun pericolo» | Un'integrazione degradata restituisce un risultato neutro, e per un motore moltiplicativo il neutro è **zero** — indistinguibile, una volta sulla mappa, da una cella davvero calma. È l'unico posto in cui questo sistema sbaglierebbe in direzione rassicurante, e il 29 settembre 2026 è successo davvero: tetto Open-Meteo esaurito, `flood` e `wildfire` a 0,0000 su ogni cella d'Italia, dipinte in fondo alla scala YlOrRd (#143). Non è ricavabile dal punteggio — una cella calma vale zero anche lei — quindi risponde il breakdown, che è l'unico a tenere il segnale grezzo: `measured()` è `fire_weather is not None` per l'incendio, `rain_mm or discharge_ratio` per l'alluvione, `True` di default perché un pericolo che poggia sul terreno è misurato anche senza meteo. Il flag viaggia su `risk_assessments.measured` e `latest_risk.measured` (NULL = storico, si legge come misurato), sale nelle viste delle tile e nel rollup per comune (`bool_or`: basta una cella), e **esce dall'indice di attenzione** — contarlo come «sotto soglia» abbassa il comune due volte, e la seconda è la peggiore, perché due pericoli concomitanti perderebbero l'incremento per colpa di un terzo ignoto. Niente di misurato ⇒ `attention` è `None`, mai 0. Sulla mappa si disegna con lo **stesso grigio** delle celle non valutate: dicono la stessa cosa, e una sesta tinta renderebbe illeggibile una scala a cinque classi. |
| `flood_forecast` ≠ the flood hazard | The `flood_forecast` YAML block and `ENABLE_FLOOD_FORECAST` tune the **hydrology component H of landslide scoring** (forecast rain + GloFAS discharge + coastal surge raise a *landslide* score). The flood **hazard** is a separate engine with its own `config/hazards/flood.yaml` and its own breakdown. They share the `FloodForecastFetchExecutor`, which is opt-in for landslide and mandatory for flood — the same signals, read for different purposes. |
| Flood: `susceptibility × max(pluvial, fluvial)` | A **maximum**, not a sum: the two triggers are different ways for one cell to end up under water, and summing lets two moderate signals invent a severe one. Susceptibility **multiplies** (unlike wildfire's additive `base`) because water goes downhill — a ridge does not flood however hard it rains next door, and below `susceptibility.floor` the engine short-circuits to zero. An unmapped cell gets `susceptibility.unmapped`, not zero: the ISPRA mosaic covers officially studied basins, and "not studied" is not "not floodable". |
| Flood signals are per node, never one per AOI | Both triggers *are* the flood engine, so a single number copied onto every cell is the failure this repo already documented for rainfall (13 mm at the Puglia centroid against 77 mm at the cells that failed). `per_node=True` samples the snapped lattice at 0.1° and each cell reads its nearest node; the AOI-level scalars stay for the landslide H component, which has always used them — changing those under the same names would move the V1 champion without a backtest. The per-node fluvial ratio divides the forecast peak by **that node's own ordinary high flow** (the `fluvial.reference_percentile` of its multi-year GloFAS series, stored in `glofas_riferimento` and filled by the nightly step within `SCHEDULER__GLOFAS_CHIAMATE_PER_NOTTE` — the **day's** GloFAS budget, minus what the sweep's river forecast will spend (one call per river node per region, cached 24 h) — paced under the hourly limit because any 429 suspends GloFAS until midnight (two years of archive weigh ~52 calls per node), rain-forecast nodes first, then susceptibility weighted by exposure — fetching two years per node inside the sweep exhausted the daily quota by 00:18 UTC and left the fluvial branch dead across Italy, #200; the sweep only reads, and asks the forecast only for nodes with a known river), never by a regional figure: dividing by the trailing month made the number incomparable between watercourses — 40 % of node-days over threshold in *every* discharge class — and the AOI-relative trickle filter that patched it silenced 101 nodes out of 105 in Emilia-Romagna, Lamone/Senio/Montone included, because 10 % of the Po is 186 m³/s (#108). A node with no reference reports `None`, which is "I don't know how big this watercourse is", not "the river is low". The **AOI-level** `river_discharge_ratio` keeps the trailing-month definition: it feeds the landslide H component and moving it would move the V1 champion without a backtest. Requests go in batches of 100 — 677 points in one query string came back as something that was not JSON. |
| Flood: the threshold's window is the window fetched | `pluvial.window_hours` is what `_flood_signals_step` passes as `horizon_hours`, so the accumulation and the threshold cannot drift apart. Comparing 72 h of rain against thresholds calibrated for 24 h would fire the trigger on an ordinary autumn. Unknown soil moisture damps at the **midpoint** between dry and saturated: skipping the damping is numerically identical to "fully saturated", the most alarming reading, so a degraded response would silently raise the trigger across a whole AOI. **The rain already fallen counts (#199)**: the window starts now, so a storm in progress leaves the forecast while it falls (Melito, 10 Oct 2026: 20 mm forecast, 152 mm on the DPC radar). The flood workflow's `ObservedRain` step samples the DPC «Merging» `CUM{pluvial.observed.hours}` accumulation (radar + gauges, 0.01°, median of the 3x3 window — one pixel read 7,348 mm) at each cell centroid, and the engine uses `max(forecast over the window, observed + forecast over the hours left)`. A frame farther than `max_age_minutes` from the valuation time is ignored, so replays and the per-cell forecast stay on the forecast. |
| Hazard is a dimension | `hazard_type` (`landslide`, `flood`, `wildfire`) is on `risk_assessments`, `model_runs`, `norm_stats`, `training_samples` and both dedup ledgers. `HazardType`/`DEFAULT_HAZARD` in `limen.core.models.hazard` is the only place the default is written. Enabling a hazard = a row in `hazards`, not a DDL change. |
| Wildfire: the weather gates the score | `score = fwi_norm × (base + fuel·f + slope·s)` — the terrain **modulates** the weather, never adds to it. A sum gave a conifer cell a weather-independent floor, so it read "Moderate" under a January downpour and the low classes were unreachable. `base` is why it is not a plain product: it is the danger a cell carries because fire arrives from outside it, so bare rock in extreme weather still scores. The three weights sum to 1, so a conifer cell on a saturated slope scores exactly its normalised FWI and the class cutoffs stay readable as EFFIS bands. The chain itself (Van Wagner 1987, `wildfire/fwi.py`) is pure and verified against the published reference day to 1e-9. |
| The FWI chain is per weather node | The three moisture codes depend only on the weather, which Open-Meteo serves at ~9 km, so `fwi_state` is keyed by `(node_lon, node_lat, day)` — NUMERIC, because float equality in a PK opens a second chain on rounding noise. Keying it by cell would store the same six numbers ~500 times a day per region. Nodes come from `build_snapped_nodes` (a **global** lattice), never `build_rain_nodes` (bbox-anchored): a persisted chain's identity must not move when an AOI boundary is redrawn. The grid step is `fwi.node_spacing_deg` in `wildfire.yaml`, **not** an env knob: changing it starts fresh chains and restarts the spin-up. A stored state older than `fwi.max_gap_days` is discarded rather than carried — `chain_days` would otherwise keep climbing until `spinup` called a broken chain settled. Retention must never delete past days: the recursion walks through them. |
| Views pin the default hazard | `mv_latest_risk` is one row per cell **per hazard**, so every consumer that counts cells filters on `hazard_type`. `v_risk_tiles` and `v_region_tiles` are pinned to `landslide` (`mv_comune_risk` is not: one row per comune and hazard since migration 051); the multi-hazard tile surface is `risk_at(z,x,y,hours_ago,hazard)`, which pg_tileserv serves with the parameter in the query string. The future has its own surface, `forecast_at(z,x,y,p_horizon,p_hazard)` (migration 060), reading `latest_forecast`: only cells ≥ Moderate, `p_hazard` NULL = worst of the forecast hazards, and **PL/pgSQL with `EXECUTE`, geometry carried through the window** — the SQL version with a second join to `cells` measured 98 s per z7 tile. A hazard whose nightly run did not happen has no future to choose: the timeline disables it instead of drawing an empty map that reads as calm. (Migration 060's header says flood is forecast only per comune: wrong — flood has per-cell rows like the others; it is immutable, so the correction lives here.) Changing horizon swaps the source with `setTiles` and does **not** rebuild the map. The SPA map uses the view for the default hazard and the function for any other — deliberately two paths, because switching the working default onto the function buys only symmetry. `NationalStrip` and the comuni list (`ComuniBoard`, with its `ComuneTrend` chart) follow the selector: a chosen hazard sets the threshold and the order of `/api/comuni?hazard=` and draws only that hazard's line, with its own class cutoffs; «Tutti i pericoli» ranks on the combined attention. |
| Hot tables are partitioned | `risk_assessments` and `model_runs` are RANGE-partitioned by **UTC** day on `computed_at`; the PK includes the partition key. Retention is `drop_expired_partitions()`, never `DELETE`. `ensure_partitions()` must run before a sweep writes: the `limen-partitions` job owns it (registered **unconditionally** — never fold it back into the cache-cleanup job, which is skipped under the pg_cron backend), the API retries it best-effort on boot, `limen partitions` runs it on demand. Rows in a `*_default` partition are a bug: retention cannot reach them. |
| Risk palette: one ramp, **not colour-only**, verified on the dark ground | Sala operativa (#155): one five-class ramp for all three hazards (nessuno quasi-fondo, basso petrolio, giallo, arancio, rosso — the Protezione civile order). The legend pairs every colour with the Italian label and the score range. `risk-colors.test.ts` enforces that **every pair** of classes stays ≥ 1.5:1 in luminance contrast, painted at 70 % over the dark basemap, under normal vision and Machado deuteranopia/protanopia/tritanopia — the design's own ramp failed it (1.09:1). Change a colour ⇒ the test says whether it still holds. Hazard identities (lilla/ciano/rosa, `HAZARD_HUE` = `--hz-*`) stay out of the ramp's warm hues. |
| Notifications = Strategy + safe gather | New channels implement `NotificationChannel` (see `notifications/base.py`). The dispatcher MUST run them via `asyncio.gather` with a `_send_safe` wrapper — one channel raising can NEVER abort the others or the workflow. |
| Alerts never invent figures | `AlertPayload.summary_it` is built deterministically from the AggregateAssessment. No LLM in the alert path. |
| Dedup is mandatory | Every dispatch path consults `alert_dispatches` via `cells_dispatched_within`. Repeat alerts for the same cell inside the window are suppressed. |
| V1 stays the baseline | The deterministic engine is **never removed** or weakened. It is the production champion until a ML challenger beats it on spatial-block CV + the §2.5 backtest (promotion gate in `limen.ml.train`). |
| Engine selection through Protocol | The workflow holds a `ScoringEngine` Protocol, never a concrete class. `SCORING__ENGINE=deterministic|ml` swaps engines without touching the workflow / API. |
| Shadow never mutates state | `ShadowChallengerExecutor` writes to `model_runs` only; `cell_results` / `assessment` / alerts remain authoritative to the champion. Persistence failures in the shadow are swallowed. |
| No spatial leakage | Training uses spatial-block CV (round-robin partition over a coarse degree grid). Random splits are forbidden — the feature store assigns `split_block` at extraction time. |
| Promotion gate is operator-driven | `limen train` sets a `promoted` MLflow tag; transitioning the model version to a stage is a manual `mlflow models transition-stage` call. Auto-promotion is forbidden. |
| KG is advisory only | The knowledge-graph sidecar enriches briefings with citations; it NEVER alters numeric scoring. `BriefingAgent` launches the KG task concurrently with the LLM and accepts an empty result on any failure. KG-down ⇒ briefing still emits, scores unchanged. |
| KG short timeout | `KG__TIMEOUT_SECONDS` (default 3s) is the per-call ceiling. `GroundingService.ground()` wraps it in a defensive `asyncio.wait_for`; an unhealthy sidecar can never extend the briefing's total wall time. |
| KG cache by (region, mechanism) | Same `(region, mechanism)` inside the TTL ⇒ same cached citations; different `top_k` requests reuse the cached set sliced client-side. Empty results are cached too, so an un-ingested sidecar doesn't generate repeat traffic. |
| Geodata is VPS-only | The `geodata` compose profile runs **only** on the self-hosted VPS / dedicated host — never on Neon, never on the operational API process. Activate explicitly: `docker compose --profile geodata up`. |
| Geodata image carries no data | The Docker image bundles Python + GDAL/PROJ + tippecanoe + the code. Datasets land in the named PostGIS volume at first `limen geodata init`. Verify with `docker image inspect` — image size ≪ data size. |
| Geodata never in critical path | The operational API reads pre-computed numeric per-cell features. `limen geodata export-features` ships those across with one upsert per cell. The MCP server is for agents; nothing in the hourly scoring path waits on it. |
| Geodata is self-contained | `geodata/` is a uv workspace member designed to be extracted into a standalone repo with one `mv`. Nothing in `geodata.*` imports from `limen.*`; Prompt-2 parsers are duplicated in `geodata/parsers.py`. |
| EFFIS is MapServer, not GeoServer | `maps.effis.emergency.copernicus.eu/gwis` is a **MapServer** CGI, and every GeoServer habit fails differently: `/gwis/ows` hangs (use `/gwis`), a wrong `typeNames` closes the connection mid-response instead of 404ing, `CQL_FILTER` is silently ignored, and `bbox` + `filter` together kill the connection. The layer is `nrt.ba.poly` with `initialdate`/`area`; dates are filtered **client-side** after a bbox request, which is cheap because one AOI's whole history is a single response (Basilicata: 515 perimeters 2012-2026, 305 KB). A sync that returns zero is a client bug, not missing credentials — that mistake cost this project a year of an empty `fire_perimeters` and three issues blocked on an accreditation nobody needed. |
| A hit rate without a base rate is unreadable | `backtest-wildfire` reports both, plus their ratio. A model that calls every summer day dangerous scores a perfect hit rate while discriminating nothing, and the base rate is what exposes it. Measure it over the **fire season only**, never the spin-up days: including them dropped Basilicata's 2025 base from 43 % to 35 % and inflated the discrimination from 1.82 to 2.27 for free. |
| Geodata URLs are official | The manifest schema refuses any URL outside `https://idrogeo.isprambiente.it/` by construction. To add a dataset, edit `datasets.yaml` (single source of truth) — no code change required. |
| MCP refresh is admin-only | The `refresh` tool requires `MCP_ADMIN_TOKEN`. Env var **unset** = refresh disabled (fail-closed). |
| The faithfulness reviewer is a Message Batch | `fedelta` (`api/jobs/fedelta_racconti.py`) is the one LLM call that bypasses the gateway: the whole evening sample goes to the Claude Message Batches API through the `anthropic` SDK (`agents` group, in the image), with `ANTHROPIC_API_KEY` and `LLM__MODELS__FEDELTA` a Claude id **other than** the briefing author (`fast-cloud` = Haiku 5.5, so the reviewer is Sonnet 5.5). The JSON is constrained by `output_config.format`; an unfinished batch is cancelled after `LLM__FEDELTA_ATTESA_MASSIMA_MINUTI` and every missing verdict is `null`, never «fedele». It replaced colibrì/GLM-5.2, removed after it OOM-killed the host on 28/10/2026: no local model that generates in tens of minutes is wired in anymore. |
| One monthly cap on Claude, checked on every call | `LLM__ANTHROPIC_BUDGET_MENSILE_USD` (10 $) covers **all** Claude spend — gateway roles on `fast-cloud`/`quality-cloud` and the batch reviewer. Every LLM call writes a `spesa_llm` row (migration 083) with the model that actually answered (`x-litellm-model-name`: a gateway fallback can make `fast-cloud` the local `chat`); before any call that can reach Claude, `agents/llm_factory/budget.py` sums the calendar month and raises `BudgetSuperatoError` at the cap, which callers treat like any model failure (deterministic text). Unreadable spend ⇒ the call does not run. LiteLLM's `max_budget` is **not** enforced (no database behind the gateway). Tokens are public (`/api/status/llm`, the Diagnostica page, «AI in pausa» in the header); dollars never are — `limen llm-spesa` and the logs only. |
| One inference endpoint | All LLM traffic goes to the LiteLLM gateway (`:8091`), never to llama-swap (`:8083`) directly (the only exception is the batch reviewer above) — routing, spend cap and local→cloud fallback all live in the gateway. `:8081` is GeoServer, not an LLM engine. From a container the host is `host.docker.internal`, never `127.0.0.1`. |
| Un'istanza Open-Meteo propria, e GloFAS no | L'API pubblica ha un tetto di 10.000 chiamate al giorno e lo sweep ne chiedeva **diecimila località a tick**, ventiquattro volte al giorno (1446 nodi FWI per quattro variabili per sette giorni, più 8538 nodi alluvione su due griglie): il tetto è saltato e alluvione e incendio hanno dato zero su tutta l'Italia per mancanza di dato, non per quiete (#142). Previsione e archivio passano da `OPENMETEO__FORECAST_URL` / `__ARCHIVE_URL` — vuote ⇒ API pubblica, quindi chi non ospita non configura — e il profilo compose `meteo` serve l'istanza su `host.docker.internal:8085`, progetto suo, porta sul loopback. **Portata e onde restano pubbliche**: GloFAS non è sul bucket AWS di Open-Meteo ("climate, flood, satellite and ensemble models are not published due to their immense size") e non si può ospitare; le onde sono uno scalare per AOI. **Con `COPERNICUS__EWDS_KEY` la previsione di portata per nodo viene dall'EWDS di Copernicus** (`cems-glofas-forecast`, corsa di controllo, la stessa che Open-Meteo serve come `forecast_v4`): scaricata in testa alla previsione per cella, salvata in `glofas_previsione` (migrazione 071), letta dallo sweep; senza chiave, o con una corsa più vecchia di `COPERNICUS__ETA_MASSIMA_GIORNI`, si torna a Open-Meteo. Stessa cella dei riferimenti: i valori che Open-Meteo restituisce sono quelli che l'EWDS etichetta **un passo più a est** della coordinata che dichiara (`cella_open_meteo`, 28 nodi su 28) — confrontare le coordinate dichiarate non lo vede, e sul Toce sbagliare cella vale un fattore dieci. `make meteo-check` dice quali variabili rispondono davvero — l'healthcheck no, risponde anche a volume vuoto. Due consumi chiedevano più volte al giorno un dato giornaliero e ora non lo fanno più: la catena FWI rilegge il giorno già scritto invece di ricamminarlo, e la previsione GloFAS sta in cache dodici ore (un degrado non si scrive mai in cache, o un 429 isolato terrebbe l'AOI a secco). |
| Copernicus attribution stays | The CEMS-Floods licence (GloFAS/EFAS) asks whoever publishes derived data to say «Contains modified Copernicus Emergency Management Service information [Year]» and never to present it as a flood warning. The notice lives in `frontend/src/lib/attribuzioni.ts` (map source for flood and the multi-hazard view, home footer, flood articles in Verifiche) and `report/regioni_pdf.py` (page footer). A new surface showing flood scores gets it too; removing it breaks the licence, not a style rule. EWDS credentials are `CDSAPI_URL`/`CDSAPI_KEY` in `.env` (read by `cdsapi` and earthkit), never in the repo. |
| Published ports bind to loopback | Docker writes its own iptables chains ahead of ufw, so the host's `default deny incoming` does not protect a published port. Every `ports:` entry uses a `LIMEN_*_BIND` variable defaulting to `127.0.0.1`; public exposure goes through a reverse proxy on 443. |

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
| `code-review` | Before pushing any non-trivial diff. Use `--fix` to apply findings. |
| `simplify` | Quick post-edit cleanup pass (same engine as `code-review --fix`). |
| `run` | When you need to actually run `limen seed` / `limen migrate` / `limen monitor-once` to see output. |
| `claude-api` | Any change to the Anthropic factory in `agents/llm_factory/` or to the LiteLLM model roles. |
| `limen-wiki` | Update `#/come-funziona` and `#/integrazioni` (sources `docs/guida/*.md`, IT + EN) from docs, YAML and code; proposes/builds anatomy figures. |
| `limen-fact-check` | Check news of landslides/floods/fires against what Limen forecast beforehand and update `#/verifiche`. |
| `anatomy` | Isometric interactive figures (vendored, MIT); `limen-wiki` says where they live in the SPA. |
| `mantine-*` | Custom Mantine components, Combobox, forms in the SPA. |
| `loop` | Poll-style monitoring of long-running ingestion/bootstrap jobs. |
| `update-config` | Permissions / hooks / env vars in `settings.json`. |
| `fewer-permission-prompts` | If we keep seeing the same approval prompt, add it to project `settings.json`. |
| `init` | Don't re-run — this file is the result. |

**Skills NOT relevant to this project:**

- All `clerk-*` skills — Limen has no user authentication at all.
- `statusline-setup`, `keybindings-help` — user-environment, not project.

---

## Sub-agents (`.claude/agents/`, versioned)

Project sub-agents follow <https://code.claude.com/docs/en/sub-agents>: one
Markdown file each, YAML frontmatter (`name`, `description`, `model`,
`effort`, `tools`/`disallowedTools`, `omitClaudeMd`, `color`) and the system
prompt in the body. Delegate to them to keep verbose output (test logs, grep
dumps, SQL results) out of the main context; invoke explicitly with
`@agent-<name>`.

**The model follows the kind of work, not the importance of the task:**

| Sub-agent | Model | Why that model | Tools | Use it when |
|-----------|-------|----------------|-------|-------------|
| `code-searcher` | `haiku`, effort low | Mechanical: grep and list `file:riga`, no judgement | Read, Grep, Glob — no CLAUDE.md | Before renaming or changing a signature; any "where is X used" |
| `gate-runner` | `haiku`, effort low | Runs commands and compresses output; never decides a fix | Bash, Read, Grep, Glob — no CLAUDE.md | After every change, before a commit (ruff, mypy, pytest unit, SPA in `node:22`) |
| `migration-reviewer` | `sonnet`, effort high | Checklist review with SQL reasoning, narrow scope | read-only + git | Every new `NNN_*.sql` |
| `db-inspector` | `sonnet`, effort medium | Writes correct SQL against a known schema; read-only transaction | Bash (psql via `docker exec`), read-only | When a number from the DB beats a guess. **Operational DB: needs user approval** |
| `source-prober` | `sonnet`, effort medium | Reads the client, reproduces the call, compares formats | Bash (curl), WebFetch, read-only | An integration returns empty/zero — before blaming credentials or quota |
| `invariant-reviewer` | `opus`, effort high | Cross-file judgement against the whole invariants table; a miss here ships a reassuring zero | read-only + git | Before every non-trivial commit/PR |
| `scoring-analyst` | `opus`, effort high | Causal reasoning across YAML → bundle → engine → breakdown, and the cost of moving the V1 champion | read-only | A score looks wrong, an event was missed, or before touching `config/hazards/*.yaml` |

Rules for adding or changing one:

- `haiku` only for work with no judgement (search, run, summarise output);
  `sonnet` for bounded analysis with a checklist; `opus` only where a wrong
  verdict costs a release (invariants, scoring). Never `opus` for search or runs.
- Mechanical agents set `omitClaudeMd: true`: this file is ~50 KB and a
  grep does not need it. Reviewers and analysts keep it — it is their metro.
- Reviewers and analysts are read-only (`disallowedTools: Edit, Write,
  NotebookEdit`): they report, the main conversation fixes.
- Descriptions are short and say *when* («Usalo in modo proattivo …»); the
  detail goes in the body. Lessons already paid for (quotas, MapServer quirks,
  `node:22` not alpine) belong in the body of the agent that needs them.
- `.gitignore` keeps `.claude/*` local except `skills/` and `agents/`.

---

## Common commands

```bash
make install                # uv sync --all-groups
make up-dev                 # docker compose: Postgres 16 + PostGIS 3.5 + pg_cron + pgvector
make seed                   # apply migrations + load Puglia/Basilicata AOIs + 1 km grid
make migrate                # apply pending SQL migrations only
uv run limen bootstrap-static   # fill cell_static_factors; skips steps whose source is unchanged
                                # (--force / LIMEN_BOOTSTRAP_FORCE=1 to recompute anyway)
uv run limen calibrate          # precompute s_static + per-AOI norm stats; S vs ISPRA gate
uv run limen backtest           # replay historical window; §2.5 hit rate / FAR / lead time
                                # (env knobs: LIMEN_BACKTEST_AOI / START / END / HIGH_LEVEL,
                                #  PRECISIONE=P1 / SORGENTI=IR,NR|stampa for the truth set)
uv run limen fwi-backfill       # rebuild the recursive FWI chain from the ERA5 archive
                                # (env knobs: LIMEN_FWI_AOI / LIMEN_FWI_DAYS)
uv run limen backtest-wildfire  # replay the FWI chain against EFFIS burnt-area perimeters
                                # (env: LIMEN_BACKTEST_WILDFIRE_AOI / _START / _END / _LEVEL)
uv run --group copernicus limen fwi-confronto  # our FWI chain vs the official Copernicus one
                                # (EWDS cems-fire-historical + EFFIS WMS mf010.*; measure only;
                                #  env: LIMEN_FWI_CONFRONTO_INIZIO / _FINE / _FONTE)
uv run limen data-status        # which per-cell static layers are loaded, and what gates the rest
uv run limen registra-verifica F # fact-check event → verifiche_eventi (+ landslide_events if a landslide)
uv run limen verifiche-report   # verified events vs forecasts per hazard, with the base rate
uv run limen raccolta-eventi    # news → Claude extractor → two outlets → verifiche_eventi (#347; daily job too)
uv run limen anticipo 077014 wildfire 2026-10-10T15:00+02:00   # how early Limen saw an event (JSON)

make data-status            # the same report
make static-data            # load every configured layer, then report
make flood-data             # same, with the note on the layer flood actually needs
uv run limen monitor-once       # run the MAF workflow once for an AOI
                                # (env knobs: LIMEN_MONITOR_AOI / CELL_LIMIT)
uv run limen serve              # start the FastAPI server on API__HOST:API__PORT (default :8080)
                                # /docs , /redoc , /health , /ready , /api/...

# Frontend (separate npm workspace under ./frontend)
( cd frontend && npm install )    # one-shot bootstrap
( cd frontend && npm run dev )    # Vite dev server on :5173
( cd frontend && npm test )       # Vitest + Testing Library
( cd frontend && npm run lint )   # ESLint
( cd frontend && npm run build )  # static dist/ for nginx / FastAPI mount
make test                   # unit + integration (testcontainers)
make test-unit              # fast, no Docker
make lint                   # ruff check
make format                 # ruff format
make typecheck              # mypy --strict on src/
make check                  # lint + typecheck + test
```

**This host (x86, `/srv/appdata/git/limen`)**: there is no Node — the SPA
gates run in `node:22` (not alpine) with `--user`, which is what
`gate-runner` does. Integration tests use the official `postgis/postgis`
image; on Apple Silicon override with `LIMEN_TEST_POSTGIS_IMAGE`
(`imresamu/postgis-arm64:16-3.5`). If `docker run hello-world` times out,
a red integration run is the disk, not the code.

---

## Repository map

```
src/limen/
├── cli/                 # `limen` entry point + ~40 subcommands (migrate, seed, bootstrap-static,
│                        # calibrate, backtest[-flood|-wildfire], fwi-backfill, monitor-once,
│                        # serve, worker, train, registra-verifica, verifiche-report, …)
├── config/
│   ├── settings.py      # pydantic-settings, env_nested_delimiter="__"
│   └── hazards/         # landslide.yaml, flood.yaml, wildfire.yaml, cascades.yaml
├── agents/
│   ├── llm_factory/     # ChatClient Protocol + Anthropic/OpenAI/Foundry/llama.cpp/Ollama + Stub + resolver
│   ├── workflow_runtime/# MAF-shaped shim: Executor, @handler, WorkflowBuilder
│   ├── executors/       # area_resolver, static_factors, meteo_fetch, observed_rain,
│   │                    # flood_forecast_fetch, fwi_update, seismic_check, fire_check,
│   │                    # sensor_fetch, risk_scoring, escalation_gate, persist_result,
│   │                    # alert_dispatch, shadow_challenger
│   ├── chat_agents/     # RiskAnalyst, Briefing, Fedelta, Traduttore + prompts/<agent>.<hazard>.it.md
│   ├── grounding/       # KG client + GroundingService (advisory citations)
│   └── workflows/       # main_workflow, forecast, forecast_history, escalation_workflow
├── api/
│   ├── main.py          # FastAPI app factory + lifespan
│   ├── dependencies.py  # AppDependencies + typed Depends() providers
│   ├── schemas.py       # Pydantic request/response DTOs
│   ├── endpoints/       # health, aoi, risk, alerts, comuni, regioni, contributi, status, tiles, a2a
│   └── jobs/            # APScheduler jobs run by `limen worker`: hourly/nowcast/firms monitoring,
│                        # briefing_enrichment, nightly, forecast_history, fedelta_racconti, …
├── a2a/                 # Agent-to-agent card, skills, service
├── mcp/                 # MCP server + tools (refresh behind MCP_ADMIN_TOKEN)
├── core/
│   ├── abstractions/    # external-source Protocols
│   ├── cascades/        # multi-hazard attention index + cascade rules
│   ├── features/        # CellFeatureBundle assembler (single V1+V2 path)
│   ├── models/          # risk DTOs, hazard.py (HazardType/DEFAULT_HAZARD), context, sensor
│   ├── scoring/         # landslide V1 engine + caine/api/seismic/post-fire/kinematic/exposure,
│   │   ├── flood/       #   flood engine + triggers + climatology
│   │   ├── wildfire/    #   wildfire engine + Van Wagner FWI + climatology
│   │   ├── ml_engine.py #   V2 ML engine (shadow challenger)
│   │   └── registry.py / resolver.py  # (hazard × implementation) + operational policy
│   ├── logging.py
│   └── llm_resolver.py
├── integrations/        # _http.py (shared client + tenacity) + one package per source:
│                        # openmeteo, copernicus (EWDS GloFAS), copernicus_ems, dpc, effis, firms,
│                        # egms, idrogeo, ingv, corine, dem, geological, imperviousness, osm,
│                        # geoserver_source, iot, static_bootstrap/
├── ml/                  # feature store, train (promotion gate), shadow, dl/, monitoring/ (drift)
├── knowledge/           # KG ontology + ingest
├── notifications/       # NotificationChannel + Telegram/MQTT/Email/Webhook + dispatcher + governance
├── observability/       # OTel tracing + metric instruments
├── report/              # daily/regional PDF + HTML reports (Copernicus attribution in regioni_pdf.py)
└── data/
    ├── db.py            # asyncpg pool + PostGIS codec
    ├── migrate.py       # idempotent SQL migrations runner
    ├── migrations/      # NNN_*.sql (001–074), immutable once applied
    ├── object_store/    # ObjectStore Protocol + filesystem | s3
    ├── caching/         # PostgresCache + CachedOpenMeteoClient
    ├── repos/           # one repo per table family (assessment, grid, fwi_state, glofas, spiegazioni, …)
    └── seed/            # italy_regions_aoi.geojson + loader

frontend/                # Vite + TypeScript + React + Mantine + MapLibre SPA
├── src/components/      # RiskMap, Timeline, HazardSelector, NationalStrip, ComuniBoard,
│                        # VerifichePage, GuidaPage, IntegrationsPage, ShadowDiagnosticsPage, …
├── src/lib/             # api-client, risk-colors, hazard, attribuzioni, i18n, overlays, …
└── src/__tests__/       # Vitest + Testing Library (risk-colors contrast test lives here)
geodata/                 # uv workspace member, self-contained (never imports limen.*)
infra/docker/            # compose files: dev, demo, geodata, geoserver, inference, meteo, observability
infra/{postgres,inference,nginx,observability,posta}/
scripts/load_static_data.sh   # the one path for static data (make up / init / static-data)
tests/{unit,integration,e2e}  # `slow` deselected by default
.claude/{skills,agents}/      # project skills + sub-agents (versioned)
```

---

## Phase boundary (what's out of scope NOW)

Do not start implementing — these land in later prompts and have explicit
extension points already:

- **Fase 1 hazard-agnostic (#57) is DONE**: `hazard_type` is a first-class
  dimension, engines resolve from a 2-D registry, config is per hazard, and
  API/MCP/A2A take an optional `hazard`.
- **Fase 3a flood (#63) is DONE and the hazard is ENABLED**: `flood.yaml`,
  the two pure triggers, the engine, the basin-scale fluvial probe, the CLMS
  imperviousness ingest and the SPA's cold palette. All three enum hazards
  now have a schema, an engine and a workflow — `check_scorable` passes for
  every one. Two caveats: without the ISPRA hydraulic mosaic loaded (it needs
  `GEOSERVER_SOURCE__DB_DSN`) every cell falls back to
  `susceptibility.unmapped` and the flood map is uniform; and **EFAS return
  periods are deliberately not implemented** — they need a CDS account plus a
  NetCDF dependency, so the client could not be exercised. GloFAS through
  Open-Meteo is the fluvial signal, and it needs no credentials.
- **Fase 2a-2b wildfire (#61, #62) is DONE and the hazard is ENABLED**: the
  FWI chain, `wildfire.yaml`, the engine, the `FwiUpdate` workflow step,
  `limen fwi-backfill`, `limen backtest-wildfire`, the WUI static factor and
  the SPA's per-hazard palette. Two caveats an operator must know:
  `landuse_code` (CORINE) and `slope_deg` (DEM) are unpopulated in most
  deployments, so the terrain term is constant and the wildfire map is
  effectively the FWI map — which is what EFFIS publishes, but not yet
  territory-modulated risk. The EFFIS perimeter service, on the other hand,
  **needs no credentials** — the earlier conclusion that it required CEMS
  accreditation was wrong, and the fix was in our own client. Measured on
  Basilicata against real perimeters: hit rate 79 % against a 43 % base rate
  in 2025, 100 % against 28 % in 2024.
- **V2 ML engine and KG grounding exist** (`core/scoring/ml_engine.py`,
  `agents/grounding/`) but stay subordinate: ML runs as the nightly shadow
  challenger, the KG only adds citations. Promotion is operator-driven.
- **Authentication is gone** (epic #69, children #70-#73): no `limen.auth`,
  no `/api/auth/*` or `/api/admin/*`, no SPID seam, no `users`/`sessions`/
  `auth_codes` tables (dropped by migration 045). An operator web area is
  explicitly parked, not planned — see memory `auth-decision`.
- DEM, CORINE and the geological map have ingest pipelines
  (`integrations/{dem,corine,geological}`), but each is opt-in on a local
  raster/shapefile: where the source is not configured the
  `cell_static_factors` columns stay NULL and the bootstrap logs
  `static_bootstrap.skip`. `limen data-status` says which are loaded.

If asked to "make it work end-to-end", clarify which phase the user wants
to advance.

---

## Where to look

- **README.md** — public-facing overview, architecture diagram, schema
  highlights, configuration reference.
- **`.env.example`** — every env var with comments (Neon + MinIO
  examples).
- **`docs/`** — `architecture.md`, `scoring-model.md`, `warning-logic.md`,
  `data-model.md`, `inference.md`, `runbook.md`, `deployment.md`, `ml.md`,
  `grounding.md`, `geodata.md`; `docs/guida/` feeds the SPA wiki.
- **Memories** at `~/.claude/projects/-srv-appdata-git-limen/memory/`
  (local to this machine; `docs/HANDOFF.md` carries what must survive a move).
- **Project doc**: `Limen_Project_Document.md` (when present at repo root)
  is the authoritative architectural reference for phases beyond the
  current scaffold.
