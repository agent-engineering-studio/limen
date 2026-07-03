# Riferimento API

La superficie HTTP di Limen è un guscio sottile sopra il workflow MAF +
i repository di Phase-1. **Nessuna logica di business negli endpoint** —
si limitano a invocare i workflow / repository. L'OpenAPI è disponibile
su `/docs` (Swagger UI) e `/redoc` (ReDoc).

L'API copre l'intero territorio nazionale (le 20 regioni ISTAT); Puglia e
Basilicata restano l'area pilota di riferimento.

La Base URL predefinita è `http://localhost:8080`. Il CORS è permissivo
di default (`API__CORS_ORIGINS=["*"]`) così che la mappa pubblica possa
effettuare richieste da qualunque host; da restringere in produzione.

L'autenticazione lato frontend (SPA Vite) usa Clerk (`@clerk/react`); la
validazione del JWT lato FastAPI è un follow-up. L'LLM in produzione gira
via Ollama (host + modello `qwen`); una chiave cloud, se presente, ha la
precedenza.

## Salute e prontezza

| Metodo | Path | Descrizione |
|---|---|---|
| `GET` | `/health` | Raggiungibilità di pool + cache + provider LLM. Restituisce sempre 200 una volta terminato il lifespan. |
| `GET` | `/ready` | Vincolato a pool + migrazioni. Restituisce 503 finché il lifespan non imposta `app.state.ready`. |

```
curl -s http://localhost:8080/health | jq
# → {"status":"ok","pool":true,"cache":true,"llm_provider":"stub"}
```

## AOI

```
curl -s http://localhost:8080/api/aoi | jq
```

Restituisce ogni riga della tabella `aoi`:

```json
{
  "items": [
    {"id": "it-puglia",     "name": "Puglia",     "kind": "region"},
    {"id": "it-basilicata", "name": "Basilicata", "kind": "region"}
  ]
}
```

## Esegui un ciclo di monitoraggio

```
curl -s -X POST http://localhost:8080/api/monitor/it-puglia \
  -H 'content-type: application/json' \
  -d '{"cell_limit": 25}' | jq
```

Corpo (opzionale):

```json
{
  "cell_limit": 25,
  "valuation_time": "2026-06-01T12:00:00+00:00"
}
```

Risposta:

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

Un AOI mancante restituisce `404`. Il workflow stesso non solleva mai
eccezioni sui fallimenti delle sorgenti esterne — degrada.

## Ultima valutazione per-AOI

```
curl -s http://localhost:8080/api/aoi/it-puglia/risk/latest | jq
```

Restituisce la valutazione persistita più recente (una riga per cella
raccolta in una lista). Include il briefing in italiano + l'output
strutturato del RiskAnalyst.

## Breakdown per cella

```
curl -s http://localhost:8080/api/cell/it-puglia%7C12%7C7/breakdown | jq
```

Restituisce i `risk_assessments.factors` grezzi (S/M/E/F/H/K + sotto-termini)
e `risk_assessments.explanation` (briefing + analisi). Le componenti di
scoring per cella sono: S (statico), M (meteo/Caine), E (sismico),
F (post-incendio), H (idraulico — ora attivo) e K (cinematico/IoT, quando
presente).

## Alert recenti

```
curl -s 'http://localhost:8080/api/alerts?threshold=High&since_hours=72&limit=50' | jq
```

Parametri di query:

* `threshold` — livello minimo, default `High`.
* `since_hours` — finestra temporale a ritroso in ore, default 72.
* `limit` — limite di paginazione, default 200, max 2000.

## Tiles (proxy pg_tileserv)

```
GET /api/tiles/{layer}/{z}/{x}/{y}.pbf
```

Restituisce un **redirect 307** verso l'istanza `pg_tileserv`
configurata (`API__PG_TILESERV_URL`). Il frontend legge lo stesso path
tramite la configurazione `apiUrl` e il redirect avviene in modo
trasparente nel browser. Quando `API__PG_TILESERV_URL` non è impostato,
l'endpoint restituisce **503**.

## OpenAPI

* `GET /docs` — Swagger UI
* `GET /redoc` — ReDoc
* `GET /openapi.json` — schema grezzo

## Forma degli errori

Gli errori usano l'envelope predefinito di FastAPI `{"detail": "..."}`.
I codici rilevanti:

| Codice | Quando |
|---|---|
| `404` | `POST /api/monitor/{aoi_id}` con un AOI sconosciuto |
| `404` | `GET /api/aoi/{id}/risk/latest` senza alcuna valutazione persistita |
| `503` | `/ready` mentre il lifespan è in fase di bootstrap |
| `503` | `/api/tiles/...` quando `API__PG_TILESERV_URL` non è configurato |
