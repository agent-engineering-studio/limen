# Limen — Claude Code project guide

> 🔴 **NUOVA MACCHINA / NUOVA SESSIONE: leggi prima [`docs/HANDOFF.md`](./docs/HANDOFF.md)**
> — stato corrente, cosa correggere dopo la migrazione su server dedicato
> (path assoluti in `.env`, Docker/PostGIS x86), lavoro in sospeso, e il
> contenuto delle memorie locali di Claude (che NON si trasferiscono col repo).

> AI multi-factor landslide-risk monitoring for the Italian territory.
> Pilot: **Puglia + Basilicata**. Current state: **implementation
> complete (0.6.0-impl-complete) — entering formal testing**.
> V1 prototype (Phases 0–8) + V1.5 in-situ IoT (Phase 9) + V2 ML
> stack (Phase 10) + KG grounding (Phase 11) + Flood / DEM / CORINE / Geological / SHAP-backed ML
> component breakdown / EFFIS bulk fallback / official ISTAT seed
> AOIs / static PMTiles overlays. Every scoring component
> (S/M/E/F/H/K) has at least one tested opt-in data-feed pipeline;
> the deterministic V1 engine remains the production champion.
> Next session opens the formal test cycle. See `README.md`,
> `docs/ml.md`, `docs/grounding.md`.

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

Every invariant has a row here. The long ones keep only the rule: the full
text and the *why* (measurements, incidents, issues) live in
`.claude/rules/<area>.md`, loaded automatically when a matching file is
touched. They bind just the same — a row ending in `→ .claude/rules/x.md`
means **read that file before changing anything the row covers**, also when
the change starts from a file outside its `paths:`. A new invariant gets a
short row here and its reasoning there.

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
| Quality gates | `ruff check` + `ruff format` clean, `mypy --strict` clean, `pytest` green before commit. **The gate is `make check`** (coverage ≥ 80 %). `slow` tests are deselected by default (`make test-slow`). An integration test that needs an AOI seeds **one**: `run_seed(only=[SEED_SMALL_AOI])`, never the twenty regions. → `.claude/rules/testing.md` |
| External HTTP | All outbound calls go through `limen.integrations._http` (`fetch_with_retry`; `call_with_retry` for streamed large downloads). A library's own retry is never used. The per-library exceptions (CDSE/GDAL, `cdsapi`, `dpc-radar`) are listed in the rule file. → `.claude/rules/integrations.md` |
| Degradation | Read-only operations that miss external sources return a *neutral result* (`None`, `[]`, `{}`) and log `integration.degraded` — they MUST NOT raise. Writes do raise. |
| Il bootstrap statico è idempotente sul **costo** | `bootstrap_static_for_aoi` salta ogni passo la cui impronta (sorgente, numero di celle, `STEP_VERSION`) non è cambiata; chiave `(aoi_id, passo)`. Cambia la *formula* ⇒ bump di `STEP_VERSION`. Tutto passa da `scripts/load_static_data.sh`: **non aggiungere un'altra variante**. → `.claude/rules/integrations.md` |
| Idempotency (sync jobs) | Compute SHA-256 over canonical-JSON of the fetched payloads, look up `dataset_versions(source, dataset, version)`. If the version exists, **skip all writes**. |
| Scoring engine purity | `MultiFactorScoringEngine.score(bundle) -> RiskScore[ComponentBreakdown]` is a *pure* function: no DB, no network, no LLM. Assembling the bundle is a separate concern. |
| Magic numbers | All weights, thresholds, sigmoid/decay params and class cutoffs live in `src/limen/config/hazards/<hazard>.yaml`, each hazard with its own schema (`SCHEMA_BY_HAZARD`). **No hard-coded constants** in scoring code — tests prove it via YAML override. Only exception: Van Wagner's FWI coefficients, in the `fwi-chain` package. → `.claude/rules/scoring.md` |
| LLM is non-authoritative | ChatAgents (RiskAnalyst, Briefing) only *reformulate* the deterministic scoring engine's numeric output. **Never** alter `score` / `breakdown`. An invariance test (`test_llm_does_not_change_numeric_breakdown`) enforces this. |
| Prompts are per hazard, and no prompt means no prose | `has_narrative(hazard)` gates both LLM nodes: a hazard without its `<agent>.<hazard>.it.md` ships **without narrative**. The async briefing re-narrates a region only on a class change or after `LLM__BRIEFING_MIN_HOURS`. Both narrative roles run on `fast-cloud`. → `.claude/rules/llm.md` |
| Agents prompts in `*.it.md` | Prompt files live next to the agent in `src/limen/agents/chat_agents/prompts/`. Loaded with `importlib.resources`. Never inline a long prompt in Python source. |
| API has no business logic | Endpoints under `src/limen/api/endpoints/` only call the Phase-4 workflow or the Phase-1 repos. New behaviour goes in `agents/` or `core/`, never in route handlers. |
| DI not globals | Everything routes need is in `AppDependencies` injected via FastAPI `Depends()`. No `from limen.x import _GLOBAL_THING` inside endpoints. |
| Three cadences, not thirteen schedules (#78) | **Hourly**: V1 only, persistence and alerts, no LLM, no shadow. **Asynchronous** (`briefing_enrichment`): narrative into `spiegazioni_regione`, never onto `risk_assessments`/`latest_risk`. **Nightly**: shadow, drift, retrain, partitions, retention — measures, never persists nor alerts. Per-cell forecast and forecast alerts run on **cron** hours (02/08/14/20), not on an interval from boot. Reintroducing a standalone schedule makes it run twice. → `.claude/rules/scheduler.md` |
| APScheduler not pg_cron, **in the `worker` process** | Periodic jobs run via APScheduler in the **`limen worker`** process, never in the API (`SCHEDULER__ENABLED=false` there). The worker runs at **one replica**: `_sweep_lock` is in-process. Do not add a distributed lock. → `.claude/rules/scheduler.md` |
| Frontend = Vite (no Next.js), and **no user auth** | Vite + React + MapLibre, public read-only map. There is **no authentication** (epic #69) and none is to be reintroduced. The only privileged actions are a sweep (CLI, or MCP behind `MCP_ADMIN_TOKEN`) and the install page's downloads (`INSTALLAZIONE__TOKEN`). → `.claude/rules/frontend.md` |
| Tile pipeline | `mv_latest_risk` is a **plain view** (one row per cell and hazard) despite the prefix; the materialised one is `mv_comune_risk`. **Always refresh it via `refresh_mv_latest_risk()`**, never `REFRESH MATERIALIZED VIEW` directly. → `.claude/rules/tiles.md` |
| Engine registry is 2-D | Engines are registered per **(hazard, implementation)** in `core/scoring/registry.py`. A new hazard = a factory + `config/hazards/<hazard>.yaml` + its schema, nothing else. `resolver.py` degrades to the V1 baseline on any V2 failure, never raising. → `.claude/rules/scoring.md` |
| Breakdown is per hazard | `RiskScore` is generic over a `HazardBreakdown` subclass with a **covariant** TypeVar; `ScoringEngine` is `Protocol[BreakdownT_co]`. PEP 695 syntax is **not** usable here (UP046 is suppressed on purpose). → `.claude/rules/scoring.md` |
| Consumers read breakdowns through projections | `CellRiskRecord` carries `breakdown: AnyHazardBreakdown`, never flattened components. Hazard-agnostic code asks the breakdown: `components()`, `factors_payload()`, `predisposition()`, `measured()`, `segnali()`. Adding a hazard touches none of them. → `.claude/rules/scoring.md` |
| «Non misurato» non è «nessun pericolo» | Un'integrazione degradata dà un neutro che per un motore moltiplicativo è **zero**, indistinguibile da una cella calma: è l'unico errore in direzione rassicurante. Risponde il breakdown con `measured()`; il flag viaggia su `risk_assessments.measured` / `latest_risk.measured` (NULL = misurato), sale nelle tile e nel rollup per comune, ed **esce dall'indice di attenzione**. Niente di misurato ⇒ `attention` è `None`, mai 0. Sulla mappa è lo stesso grigio delle celle non valutate. → `.claude/rules/scoring.md` |
| `flood_forecast` ≠ the flood hazard | The `flood_forecast` YAML block and `ENABLE_FLOOD_FORECAST` tune the **hydrology component H of landslide scoring**. The flood **hazard** is a separate engine with its own `flood.yaml`. They share `FloodForecastFetchExecutor` (opt-in for landslide, mandatory for flood). → `.claude/rules/flood.md` |
| Flood: `susceptibility × max(pluvial, fluvial)` | A **maximum**, not a sum, and susceptibility **multiplies**. An unmapped cell gets `susceptibility.unmapped`, not zero: "not studied" is not "not floodable". → `.claude/rules/flood.md` |
| Flood signals are per node, never one per AOI | `per_node=True` on the snapped 0.1° lattice; the fluvial ratio divides by **that node's own** reference flow (`glofas_riferimento`, filled by the nightly step within the day's GloFAS budget — the sweep only reads). No reference ⇒ `None`. The **AOI-level** scalars keep their old definition: they feed landslide H, and moving them moves the V1 champion without a backtest. → `.claude/rules/flood.md` |
| Flood: the threshold's window is the window fetched | `pluvial.window_hours` is the `horizon_hours` fetched. Unknown soil moisture damps at the **midpoint**. Rain already fallen counts: `max(forecast, observed + forecast over the hours left)`, observed from the DPC radar accumulation with the corrupted-frame check. → `.claude/rules/flood.md` |
| Hazard is a dimension | `hazard_type` (`landslide`, `flood`, `wildfire`) is on `risk_assessments`, `model_runs`, `norm_stats`, `training_samples` and both dedup ledgers. `HazardType`/`DEFAULT_HAZARD` in `limen.core.models.hazard` is the only place the default is written. Enabling a hazard = a row in `hazards`, not a DDL change. |
| Wildfire: the weather gates the score | `score = fwi_norm × (base + fuel·f + slope·s)`, weights summing to 1 — the terrain **modulates** the weather, never adds to it. → `.claude/rules/wildfire.md` |
| The FWI chain is per weather node | `fwi_state` is keyed by `(node_lon, node_lat, day)`, NUMERIC, on the **global** lattice of `build_snapped_nodes` (never `build_rain_nodes`). The step is `fwi.node_spacing_deg` in the YAML, not an env knob. A state older than `fwi.max_gap_days` is discarded. Retention must never delete past days. → `.claude/rules/wildfire.md` |
| Views pin the default hazard | Every consumer that counts cells filters on `hazard_type`. `v_risk_tiles` / `v_region_tiles` are pinned to `landslide`; the multi-hazard surface is `risk_at(z,x,y,hours_ago,hazard)`, the future is `forecast_at(z,x,y,p_horizon,p_hazard)` (PL/pgSQL with `EXECUTE`, on purpose). The SPA deliberately uses the view for the default hazard and the function for the others. → `.claude/rules/tiles.md` |
| Hot tables are partitioned | `risk_assessments` and `model_runs` are RANGE-partitioned by **UTC** day. Retention is `drop_expired_partitions()`, never `DELETE`. `ensure_partitions()` runs before a sweep writes (`limen-partitions`, registered unconditionally). Rows in a `*_default` partition are a bug. → `.claude/rules/db.md` |
| Risk palette: one ramp, **not colour-only**, verified on the dark ground | One five-class ramp for all three hazards, every colour paired with its Italian label and score range. `risk-colors.test.ts` enforces ≥ 1.5:1 luminance contrast for **every pair**, on the dark basemap, under normal and colour-blind vision. Hazard identity hues stay out of the ramp. → `.claude/rules/frontend.md` |
| Notifications = Strategy + safe gather | New channels implement `NotificationChannel` (see `notifications/base.py`). The dispatcher MUST run them via `asyncio.gather` with a `_send_safe` wrapper — one channel raising can NEVER abort the others or the workflow. |
| Alerts never invent figures | `AlertPayload.summary_it` is built deterministically from the AggregateAssessment. No LLM in the alert path. |
| Dedup is mandatory | Every dispatch path consults `alert_dispatches` via `cells_dispatched_within`. Repeat alerts for the same cell inside the window are suppressed. |
| V1 stays the baseline | The deterministic engine is **never removed** or weakened. It is the production champion until a ML challenger beats it on spatial-block CV + the §2.5 backtest (promotion gate in `limen.ml.promozione`: the CV half in `limen train`, hit rate / FAR / lead time from `limen backtest` with `LIMEN_BACKTEST_SFIDANTE`, the challenger alerting at the V1's cell-hour rate — #483). |
| Engine selection through Protocol | The workflow holds a `ScoringEngine` Protocol, never a concrete class. `SCORING__ENGINE=deterministic|ml` swaps engines without touching the workflow / API. |
| Shadow never mutates state | `ShadowChallengerExecutor` writes to `model_runs` only; `cell_results` / `assessment` / alerts remain authoritative to the champion. Persistence failures in the shadow are swallowed. |
| No spatial leakage | Training uses spatial-block CV (round-robin partition over a coarse degree grid). Random splits are forbidden — the feature store assigns `split_block` at extraction time. |
| Promotion gate is operator-driven | `limen train` sets `gate_validazione`, `limen backtest` with `LIMEN_BACKTEST_SFIDANTE` sets the `promoted` MLflow tag; transitioning the model version to a stage is a manual `mlflow models transition-stage` call. Auto-promotion is forbidden. |
| KG is advisory only | The knowledge-graph sidecar enriches briefings with citations; it NEVER alters numeric scoring. `BriefingAgent` launches the KG task concurrently with the LLM and accepts an empty result on any failure. KG-down ⇒ briefing still emits, scores unchanged. |
| KG short timeout | `KG__TIMEOUT_SECONDS` (default 3s) per call, wrapped in a defensive `asyncio.wait_for` by `GroundingService.ground()`. → `.claude/rules/llm.md` |
| KG cache by (region, mechanism) | Same `(region, mechanism)` inside the TTL ⇒ same cached citations; empty results are cached too. → `.claude/rules/llm.md` |
| EFFIS is MapServer, not GeoServer | `maps.effis.emergency.copernicus.eu/gwis` is a **MapServer** CGI: GeoServer habits fail silently or kill the connection. Layer `nrt.ba.poly`, bbox request, dates filtered client-side. A sync that returns zero is a client bug, not missing credentials. The client is the `effis-client` package; retry and degradation stay in Limen. → `.claude/rules/wildfire.md` |
| A hit rate without a base rate is unreadable | `backtest-wildfire` reports hit rate, base rate and their ratio, over the **fire season only**, never the spin-up days. → `.claude/rules/wildfire.md` |
| MCP admin tools are token-gated | The mutating `limen-ops` MCP tools (`tool_run_monitor`, `tool_build_report`, `tool_forecast_history`) require `MCP_ADMIN_TOKEN`. Env var **unset** = those tools disabled (fail-closed). |
| The install token is not a login | `INSTALLAZIONE__TOKEN` gates the `POST /api/installazione/*` actions through `TokenInstallazioneDep` (header `X-Limen-Token`); reading the state stays public. One shared secret, unset ⇒ disabled (fail-closed). **No users, no sessions**: do not grow it into accounts or an operator area. → `.claude/rules/frontend.md` |
| The faithfulness reviewer is a Message Batch | `fedelta` is the one LLM call that bypasses the gateway: the Claude Message Batches API through the `anthropic` SDK, with `LLM__MODELS__FEDELTA` a Claude id **other than** the briefing author. A missing verdict is `null`, never «fedele». No slow local model is wired in anymore. → `.claude/rules/llm.md` |
| One monthly cap on Claude, checked on every call | `LLM__ANTHROPIC_BUDGET_MENSILE_USD` covers **all** Claude spend. Every LLM call writes a `spesa_llm` row; `agents/llm_factory/budget.py` checks the month before any call that can reach Claude and raises `BudgetSuperatoError` (callers fall back to deterministic text). Unreadable spend ⇒ the call does not run. Tokens are public, dollars never. → `.claude/rules/llm.md` |
| One inference endpoint | All LLM traffic goes to the LiteLLM gateway (`:8091`), never to llama-swap (`:8083`) directly (only exception: the batch reviewer). From a container the host is `host.docker.internal`, never `127.0.0.1`. → `.claude/rules/llm.md` |
| Un'istanza Open-Meteo propria, e GloFAS no | Previsione e archivio passano da `OPENMETEO__FORECAST_URL` / `__ARCHIVE_URL` (vuote ⇒ API pubblica, tetto 10.000 chiamate/giorno); il profilo compose `meteo` serve l'istanza propria. **Portata (GloFAS) e onde restano pubbliche**; con `COPERNICUS__EWDS_KEY` la previsione di portata per nodo viene dall'EWDS (`glofas_previsione`). Un degrado non si scrive mai in cache. `make meteo-check` dice cosa risponde davvero. → `.claude/rules/integrations.md` |
| Copernicus attribution stays | Every surface showing flood scores carries «Contains modified Copernicus Emergency Management Service information [Year]» (`frontend/src/lib/attribuzioni.ts`, `report/regioni_pdf.py`) and never presents it as a flood warning. Removing it breaks the licence. EWDS credentials live in `.env`, never in the repo. → `.claude/rules/frontend.md` |
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

Not relevant here: every `clerk-*` skill (Limen has no user authentication).

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
| `invariant-reviewer` | `opus`, effort high | Cross-file judgement against the whole invariants table and `.claude/rules/`; a miss here ships a reassuring zero | read-only + git | Before every non-trivial commit/PR |
| `scoring-analyst` | `opus`, effort high | Causal reasoning across YAML → bundle → engine → breakdown, and the cost of moving the V1 champion | read-only | A score looks wrong, an event was missed, or before touching `config/hazards/*.yaml` |

Rules for adding or changing one:

- `haiku` only for work with no judgement (search, run, summarise output);
  `sonnet` for bounded analysis with a checklist; `opus` only where a wrong
  verdict costs a release (invariants, scoring). Never `opus` for search or runs.
- Mechanical agents set `omitClaudeMd: true`: a grep does not need this
  file. Reviewers and analysts keep it — it is their metro.
- Reviewers and analysts are read-only (`disallowedTools: Edit, Write,
  NotebookEdit`): they report, the main conversation fixes.
- Descriptions are short and say *when* («Usalo in modo proattivo …»); the
  detail goes in the body. Lessons already paid for (quotas, MapServer quirks,
  `node:22` not alpine) belong in the body of the agent that needs them.
- `.gitignore` keeps `.claude/*` local except `skills/`, `agents/` and
  `rules/`.

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
uv run limen dem-tiles [--aoi it-puglia]   # relief tiles (terrain-RGB PMTiles) from LIMEN_DEM_RASTER (#318)
uv run limen registra-verifica F # fact-check event → verifiche_eventi (+ landslide_events if a landslide)
uv run limen verifiche-report   # verified events vs forecasts per hazard, with the base rate
uv run limen raccolta-eventi    # news → Claude extractor → two outlets → verifiche_eventi (#347; daily job too)
uv run limen misura --pericolo wildfire --feature slope_deg --stima 2021-2023 --verifica 2024-2026
                                # read-only stratified AUC + observed/expected of a per-cell feature (#480)
uv run limen importa-eventi F --ente N --licenza L  # an authority's dated events (CSV/GeoJSON) → verifiche_eventi (#509)
uv run limen archivia-report R.md  # a measurement report + its provenance (commit, model_version, env) → docs/misure (#481)
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

Only what `ls` does not say:

```
src/limen/
├── cli/                 # `limen` entry point, ~40 subcommands
├── config/hazards/      # landslide|flood|wildfire|cascades.yaml — every scoring number
├── agents/
│   ├── llm_factory/     # ChatClient Protocol + providers + resolver + budget
│   ├── workflow_runtime/# MAF-shaped shim: Executor, @handler, WorkflowBuilder
│   ├── executors/       # one workflow step each (fetch, scoring, persist, alert, shadow)
│   ├── chat_agents/     # RiskAnalyst, Briefing, Fedelta, Traduttore + prompts/<agent>.<hazard>.it.md
│   └── workflows/       # main_workflow, forecast, forecast_history, escalation_workflow
├── api/
│   ├── endpoints/       # routes only, no business logic
│   └── jobs/            # APScheduler jobs, run by `limen worker`
├── core/
│   ├── cascades/        # multi-hazard attention index + cascade rules
│   ├── features/        # CellFeatureBundle assembler (single V1+V2 path)
│   └── scoring/         # landslide V1 engine at the top level; flood/, wildfire/;
│                        # ml_engine.py (shadow); registry.py + resolver.py
├── integrations/        # _http.py (shared client + tenacity) + one package per source;
│                        # static_bootstrap/
├── ml/                  # feature store, train (promotion gate), shadow, monitoring/ (drift)
└── data/                # db.py (pool + PostGIS codec), migrate.py, migrations/ (immutable),
                         # object_store/, caching/, repos/ (one per table family), seed/

frontend/                # Vite + TypeScript + React + Mantine + MapLibre SPA (own npm workspace)
infra/docker/            # compose files: dev, demo, geoserver, inference, meteo, observability
scripts/load_static_data.sh   # the one path for static data
.claude/{skills,agents,rules}/  # versioned
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
  every one. Two caveats: without the ISPRA hydraulic mosaic loaded (`make static-data`
  downloads it and `limen carica-vettori` loads it into Limen's own database,
  schema `sorgenti`, #426 — GeoServer is optional) every cell falls back to
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
  `grounding.md`; `docs/guida/` feeds the SPA wiki.
- **Memories** at `~/.claude/projects/<slug of the repo path>/memory/`
  (local to each machine; `docs/HANDOFF.md` carries what must survive a move).
- **Project doc**: `Limen_Project_Document.md` (when present at repo root)
  is the authoritative architectural reference for phases beyond the
  current scaffold.
