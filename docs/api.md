# API reference

Limen's HTTP surface is a thin shell over the MAF workflow + Phase-1
repos. **No business logic in endpoints** — they call workflows /
repos. OpenAPI lives at `/docs` (Swagger UI) and `/redoc` (ReDoc).

Base URL defaults to `http://localhost:8080`. CORS is permissive by
default (`API__CORS_ORIGINS=["*"]`) so the public map can fetch from
any host; tighten in production.

## Health & readiness

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Pool + cache + LLM provider reachability. Always 200 once the lifespan finishes. |
| `GET` | `/ready` | Gated on pool + migrations. Returns 503 until the lifespan flips `app.state.ready`. |

```
curl -s http://localhost:8080/health | jq
# → {"status":"ok","pool":true,"cache":true,"llm_provider":"stub"}
```

## AOI

```
curl -s http://localhost:8080/api/aoi | jq
```

Returns every row in the `aoi` table:

```json
{
  "items": [
    {"id": "it-puglia",     "name": "Puglia",     "kind": "region"},
    {"id": "it-basilicata", "name": "Basilicata", "kind": "region"}
  ]
}
```

## Run a monitoring cycle

```
curl -s -X POST http://localhost:8080/api/monitor/it-puglia \
  -H 'content-type: application/json' \
  -d '{"cell_limit": 25}' | jq
```

Body (optional):

```json
{
  "cell_limit": 25,
  "valuation_time": "2026-06-01T12:00:00+00:00"
}
```

Response:

```json
{
  "aoi_id": "it-puglia",
  "assessment_id": 4567,
  "assessment": {
    "aoi_id": "it-puglia",
    "model_version": "limen-deterministic-v1",
    "valuation_time": "2026-06-01T12:00:03.412678+00:00",
    "n_cells": 25,
    "cells_high_or_above": 2,
    "cells_by_level": {"None": 21, "Low": 2, "High": 1, "VeryHigh": 1},
    "top_cells": [
      {"cell_id": "it-puglia|12|7", "score": 0.81, "level": "VeryHigh", ...}
    ],
    "analysis": {"driver": "meteo_trigger", "anomalies": [...], ...},
    "briefing_it": "Le condizioni osservate ..."
  },
  "cells_scored": 25,
  "high_or_above": 2,
  "dispatched_alerts": [...]
}
```

A missing AOI returns `404`. The workflow itself never raises on
external-source failures — it degrades.

## Latest per-AOI assessment

```
curl -s http://localhost:8080/api/aoi/it-puglia/risk/latest | jq
```

Returns the most recent persisted assessment (one row per cell rolled
into a list). Includes the Italian briefing + the structured
RiskAnalyst output.

## Per-cell breakdown

```
curl -s http://localhost:8080/api/cell/it-puglia%7C12%7C7/breakdown | jq
```

Returns the raw `risk_assessments.factors` (S/M/E/F/H + sub-terms) and
`risk_assessments.explanation` (briefing + analysis).

## Recent alerts

```
curl -s 'http://localhost:8080/api/alerts?threshold=High&since_hours=72&limit=50' | jq
```

Query params:

* `threshold` — minimum level, default `High`.
* `since_hours` — trailing window in hours, default 72.
* `limit` — pagination cap, default 200, max 2000.

## Tiles (pg_tileserv proxy)

```
GET /api/tiles/{layer}/{z}/{x}/{y}.pbf
```

Returns a **307 redirect** to the configured `pg_tileserv` instance
(`API__PG_TILESERV_URL`). The frontend reads the same path via the
`apiUrl` config and the redirect happens transparently in the browser.
When `API__PG_TILESERV_URL` is unset, the endpoint returns **503**.

## OpenAPI

* `GET /docs` — Swagger UI
* `GET /redoc` — ReDoc
* `GET /openapi.json` — raw schema

## Error shape

Errors are FastAPI's default `{"detail": "..."}` envelope. The notable
codes:

| Code | When |
|---|---|
| `404` | `POST /api/monitor/{aoi_id}` with an unknown AOI |
| `404` | `GET /api/aoi/{id}/risk/latest` with no persisted assessment |
| `503` | `/ready` while the lifespan is bootstrapping |
| `503` | `/api/tiles/...` when `API__PG_TILESERV_URL` is unconfigured |
