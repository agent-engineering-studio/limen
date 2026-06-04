# Knowledge-graph grounding (V2.x)

The KG layer adds **citable scientific grounding** to the Italian
briefings. It is **advisory only**: it ships citations as Markdown
appended to the LLM narrative, never alters numeric scoring outputs,
and degrades silently when the sidecar is unreachable.

## Architecture

```
                +-------------------+        advisory + async + short timeout
                |  BriefingAgent    | ──────────────────────────────────────┐
                +---------+---------+                                       ▼
                          │ awaits at the end of LLM call         +--------------------+
                          │ (parallel — no extra latency)         |  KG sidecar        |
                          ▼                                       |  Neo4j + Redis +   |
                +-------------------+    POST /query              |  Ollama + FastAPI  |
                |  GroundingService | ───────────────────────────►|  + MCP             |
                +---------+---------+                             +---------+----------+
                          │  (region, mechanism) cache                      │
                          ▼                                                  │
                +-------------------+                                        │
                |  PostgresCache    |                                        │
                |  (app_cache)      |◄───────────────────────────────────────┘
                +-------------------+
```

* **Champion guarantee**: the deterministic V1 engine + the V2 ML
  champion's `cell_results` / `assessment` / alerts are NEVER affected
  by KG state — by construction.
* **Sidecar**: the team's `knowledge-graph` repo deploys Neo4j + Redis
  + Ollama + FastAPI + MCP. Limen consumes it via REST (one less
  moving piece than MCP for now); the same payload shape works with
  the MCP tool surface.

## Configuration

| Env var | Default | What it does |
|---|---|---|
| `KG__ENABLED` | `false` | Master switch. With `false` the grounding code path is dormant. |
| `KG__BASE_URL` | `http://localhost:8000` | Sidecar HTTP endpoint. |
| `KG__THREAD_ID` | `landslide-kb` | Logical corpus on the sidecar — keep stable across deployments. |
| `KG__TIMEOUT_SECONDS` | `3.0` | Per-call ceiling. The briefing **never** stalls beyond this. |
| `KG__CACHE_TTL_SECONDS` | `3600` | (region, mechanism) cache lifetime in `app_cache`. |
| `KG__API_TOKEN` | — | Optional bearer for the sidecar. |
| `KG__TOP_K` | `4` | Passages requested per query. |

## Ontology (project doc §2.8)

| Entity | Description |
|---|---|
| `Paper` | Scientific paper or technical report about landslides. |
| `Author` | Author of a Paper. |
| `RainfallThreshold` | Caine-style intensity-duration threshold. |
| `TriggerMechanism` | rainfall / seismic / post-fire / anthropic. |
| `LandslideType` | Movement type (slide, flow, fall, topple, complex). |
| `Lithology` | Rock/soil type relevant to slope stability. |
| `Region` / `Area` | Italian region or sub-regional area. |
| `HistoricalEvent` | Documented past landslide event. |
| `NormativePlan` | PAI / regulatory plans. |

Relations: `DEFINES_THRESHOLD`, `VALID_FOR_REGION`, `TRIGGERED_BY`,
`DOCUMENTED_IN`, `OCCURRED_IN`, `SUPPORTS_PARAMETER`. The canonical
source is `src/limen/knowledge/ontology.py`; the ingestion job ships
a normalised copy of `ONTOLOGY.to_kg_payload()` to the sidecar.

## Corpus ingestion (`limen ingest-kb`)

```bash
LIMEN_KB_CORPUS=./kb-corpus \
  KG__ENABLED=true \
  KG__BASE_URL=http://localhost:8000 \
  uv run limen ingest-kb
```

The walker scans the corpus root and maps these suffixes to ontology
kinds:

| Suffix | Kind |
|---|---|
| `*.paper.{md,txt}` | `paper` |
| `*.pai.md` | `pai_plan` |
| `*.ispra.md` | `ispra_report` |
| `*.iffi.md` | `iffi_event` |
| `*.briefing.md` | `limen_briefing` |

Idempotency is layered:

1. The sidecar dedupes by document `source` (natural key).
2. Limen hashes the serialised request body and registers it in
   `dataset_versions`. A re-run that hashes identically issues
   **zero** HTTP calls.

## Provider coherence (§3.7)

The KG sidecar's inference uses the same LLM the rest of Limen does.
The `infra/docker/docker-compose.demo.yml` `kg` profile threads
`ANTHROPIC_API_KEY`, `OPENAI_API_KEY` and `OLLAMA_BASE_URL` from the
host environment into the sidecar so the resolver picks the same
provider in both processes.

On the Aruba prod target this typically means **Ollama is the primary
provider** for the sidecar too (no cloud egress on hourly hot-paths),
with the cloud keys as fallback. Switching providers happens once at
the host level — neither Limen nor the sidecar code needs to know.

## EU data residency (§3.13)

Both the API and the KG sidecar run in the same EU-region Aruba VPS.
The default `docker-compose.demo.yml` `kg` profile is wired so the
sidecar receives Italian-source PAI / ISPRA / CNR-IRPI material and
returns citations referencing them — no third-party hop. Neon (prod
DB option) is EU-region. The shared Ollama runtime stays on-premise.

## Critical-path invariance

The Phase-11 acceptance criteria require:

* With KG up → briefings carry citations for the cell's driver.
* With KG down / slow → briefings still emit (no citations), numbers
  unchanged, workflow does not stall.

This is enforced by three lines of defence:

1. `GroundingService.ground()` wraps the client call in
   `asyncio.wait_for(..., timeout=kg.timeout_seconds)`.
2. `BriefingAgent.brief()` launches the KG task **concurrently** with
   the LLM call; it never sequences them. Total wall time ≤
   `max(LLM, kg.timeout_seconds)`.
3. Every exception path in `KgClient` / `GroundingService` /
   `BriefingAgent._append_citations` returns the un-cited narrative.
   The deterministic scoring engine doesn't see this code path at all.

## Local demo

```bash
# Run Postgres + API + (optionally) the KG sidecar in the same compose:
docker compose -f infra/docker/docker-compose.demo.yml \
  --profile frontend --profile kg \
  up -d
```

The sidecar's actual image is owned by the
`agent-engineering-studio/knowledge-graph` repo — pin a tagged
version in production. Limen's runtime contract is the narrow
schema in `src/limen/knowledge/schema.py`.
