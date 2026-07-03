# Limen

> **Monitoraggio AI multi-fattore del rischio frana per il territorio italiano.**
> **Copertura nazionale — tutte le 20 regioni ISTAT** su griglia 1 km²
> (~312k celle); validato sul pilota Puglia + Basilicata.

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-green.svg)](./LICENSE)
[![uv](https://img.shields.io/badge/managed%20by-uv-261230)](https://github.com/astral-sh/uv)
[![ruff](https://img.shields.io/badge/lint-ruff-261230)](https://github.com/astral-sh/ruff)
[![mypy --strict](https://img.shields.io/badge/typed-mypy%20--strict-blue)](http://mypy-lang.org/)

Limen ("soglia" in latino) unisce **morfologia, geologia, umidità del
suolo, piogge, sismicità, incendi e archivi storici** in un punteggio di
rischio frana per ogni cella di un'area italiana. Stack: Python 3.12 +
FastAPI + PostgreSQL 16 + PostGIS, frontend Vite + React + MapLibre,
notifiche multi-canale. Il sistema è costruito attorno a un Multi-Agent
Framework (MAF) che orchestra ingestione → scoring → spiegazione, con un
data layer portabile tra Docker locale, Neon (serverless) e qualsiasi
PostgreSQL gestito.

## Avvio rapido

```bash
git clone https://github.com/agent-engineering-studio/limen.git
cd limen
uv sync --all-groups
make up                     # Postgres+PostGIS + GeoServer (mcp-geoserver) + frontend
make init                   # migrate → seed 20 regioni → ITALICA → bootstrap → calibrate
uv run limen serve          # FastAPI su http://localhost:8080/docs
( cd frontend && npm ci && npm run dev )   # mappa su http://localhost:5173
```

`make init` è idempotente e ricostruisce tutti i dati su una macchina
nuova: applica le migrazioni, semina le 20 regioni ISTAT (griglia 1 km²),
scarica il catalogo eventi frana **e-ITALICA** da Zenodo (truth set del
backtest §2.5), popola i fattori statici per cella (IFFI + PAI dal
PostGIS di GeoServer + slope da DTM) e calibra `s_static`.

Su **Neon** (dev/test serverless): impostare `DB__CONNECTION_STRING` con
`?sslmode=require` e `SCHEDULER__CACHE_CLEANUP=apscheduler`, nient'altro
— `pg_cron` viene saltato e l'APScheduler in-process prende in carico i
job periodici. In **produzione** (host Docker self-hosted, nessun cloud
provider): `docker compose -f infra/docker/docker-compose.demo.yml up -d
--build`. Provider LLM risolto per precedenza `LLM__PROVIDER` >
`ANTHROPIC_API_KEY` > `OPENAI_API_KEY` > credenziali Foundry > Ollama;
in locale/produzione si usa **Ollama** (host, modello qwen).

Approfondimenti: [`docs/architecture.md`](./docs/architecture.md),
[`docs/api.md`](./docs/api.md),
[`docs/deployment.md`](./docs/deployment.md),
[`docs/scoring-model.md`](./docs/scoring-model.md),
[`docs/runbook.md`](./docs/runbook.md).

Il motore V1 è una combinazione lineare pesata **pura** e interpretabile
(§2.4 del project doc) che legge ogni peso, soglia e cutoff di classe da
[`src/limen/config/regional_thresholds.yaml`](./src/limen/config/regional_thresholds.yaml).
Nessuna costante cablata nel codice di scoring. Nessun LLM. Nessun I/O.
La stessa interfaccia `CellFeatureBundle` accetta anche il motore ML V2.

---

## Componenti e sorgenti

| Sorgente | Cosa ingeriamo | Cadenza | Implementazione |
|---|---|---|---|
| **Open-Meteo** | precip oraria, umidità del suolo 0–7 / 7–28 cm, neve (forecast); precip cumulata (archivio) | live, cache 30 min | `integrations/openmeteo/` + `CachedOpenMeteoClient` |
| **ISPRA (PostGIS di GeoServer)** | inventario IFFI (frane/aree/dgpv, tutte le regioni), mosaico PAI frana; il mosaico idraulica alimenta il componente `H` | all'init / settimanale | `integrations/geoserver_source/` legge il PostGIS di mcp-geoserver |
| **INGV** | eventi FDSN (mag ≥ 3.5, ultimi 7 g, bbox AOI); griglia ShakeMap | poll event-driven | `integrations/ingv/` + `seismic_repo` + `ObjectStore` |
| **EFFIS** | perimetri aree bruciate; fallback bulk Shapefile | batch settimanale | `integrations/effis/` |
| **Bootstrap statico** | per cella: `iffi_density_500` (entro 500 m dalla cella), `distance_to_iffi_m`, `pai_class_norm`, `slope_deg` (DTM) — SQL PostGIS set-based | one-shot CLI | `integrations/static_bootstrap/` + `limen bootstrap-static` |
| **Motore di scoring (V1)** | soglia Caine I/D (ri-tarata su ITALICA), API sigmoide, finestra post-incendio, decadimento sismico, aggregatore pesato + 5 classi | puro (no I/O) | `core/scoring/` + `MultiFactorScoringEngine` |
| **Calibrate** | stat di normalizzazione per-AOI; precompute `s_static` | one-shot | `limen calibrate` + `reports/calibrate_<aoi>.md` |
| **Ingest eventi** | catalogo **e-ITALICA** (frane innescate da pioggia, datate, tutta Italia) — truth set del backtest | one-shot, auto-download Zenodo | `limen ingest-events` |
| **Backtest** | replay di una finestra storica con pioggia antecedente **CERRA** (5.5 km) + truth set e-ITALICA → hit rate / FAR / lead time vs target §2.5 | one-shot | `limen backtest` + `reports/backtest_*.md` |
| **Workflow MAF (V1)** | AreaResolver → StaticFactors → MeteoFetch → SeismicCheck → FireCheck → \[SensorFetch?\] → RiskScoring → EscalationGate → RiskAnalyst → Briefing → PersistResult → AlertDispatch | one-shot CLI | `agents/` + `limen monitor-once` |
| **Provider LLM** | precedenza `LLM__PROVIDER` > Anthropic > OpenAI > Foundry > Ollama; il resolver salta i provider cloud senza SDK e cade su Ollama (solo httpx). Briefing in italiano; RiskAnalyst restituisce JSON tipizzato. | risolto all'avvio | `agents/llm_factory/resolve_llm_factory` |
| **API HTTP** | `/health` + `/ready`, `POST /api/monitor/{aoi}`, `GET /api/aoi/{id}/risk/latest`, `GET /api/cell/{id}/breakdown`, `GET /api/aoi`, `GET /api/alerts`, `/api/tiles/...`, OpenAPI su `/docs` e `/redoc` | FastAPI / uvicorn | `api/` + `limen serve` |
| **Job periodici** | workflow MAF orario, sync ISPRA settimanale, cache cleanup | APScheduler in-process | `api/jobs/` |
| **Vector tiles** | matview `mv_latest_risk` (grid_cells ⨝ ultimo risk_assessment per cella), rinfrescata da `refresh_mv_latest_risk()`; servita da **pg_tileserv** | per ciclo di monitoraggio | migrazione `007_map_views.sql` |
| **Frontend** | SPA Vite + TS + React + **MapLibre GL JS**: `RiskMap` (vector tiles, palette 5 classi ColorBrewer YlOrRd), `LegendPanel` (etichette + range, non solo colore), `AlertList`, `CellPopup`, `TimelineSlider`; overlay PMTiles PAI/IFFI opt-in | pubblico, read-only | `frontend/` |
| **Notifiche** | Protocol `NotificationChannel` + Telegram / MQTT / Email; dispatcher in parallelo con isolamento eccezioni per canale; dedup su `alert_dispatches` | per tick del workflow | `notifications/` |

---

## Perché queste scelte

| Decisione | Motivazione |
|-----------|-------------|
| **PostgreSQL 16 + PostGIS engine-agnostic** (no Supabase, no BaaS, no ORM) | Stesso SQL e stesso codice su Docker locale, Neon o self-hosted. Cambia solo `DB__CONNECTION_STRING`. |
| **`asyncpg` + codec PostGIS custom** | Le geometrie viaggiano come oggetti Shapely, niente boilerplate WKB, niente lock-in di sessione ORM. |
| **`pg_cron` opzionale** | Neon non lo supporta. L'**APScheduler** in-process esegue gli stessi job periodici quando l'estensione manca. |
| **Object storage dietro Protocol** (`filesystem` / `s3`) | I byte raster non vanno mai nel DB. PostGIS memorizza solo riferimenti (path + bbox + CRS + checksum). Il backend `s3` punta a qualsiasi endpoint S3-compatibile (MinIO, R2, B2) via `OBJECT_STORE__ENDPOINT_URL` — mai SDK cloud. |
| **Migrazioni SQL semplici** | Niente Alembic, niente ORM. Un runner con tabella `schema_migrations` + checksum. Comportamento identico su ogni Postgres. |
| **Pydantic v2 + `structlog`** | Configurazione tipizzata e log strutturati senza reinventare. |
| **`uv` + layout `src/`** | Gestione dipendenze lockfile-first; il pacchetto non può importare per errore il proprio codice di test. |
| **GeoServer come sorgente dati generica** | mcp-geoserver pubblica gli opendata ISPRA nel suo PostGIS; la semantica ISPRA vive solo nel loader Limen, non nell'MCP (che resta generico). |

---

## Calibrazione e validazione (§2.5)

Il ciclo di test formale ha tarato il motore sui dati reali:

- **Soglia Caine I/D** ri-derivata dal catalogo **e-ITALICA** (5974 coppie
  intensità-durata misurate da pluviometri), inviluppo inferiore T5 per
  macroregione. La soglia storica lasciava il 36% delle frane reali sotto
  soglia; ora ~95% sono sopra soglia.
- **Sorgente pioggia**: **CERRA** (5.5 km) al posto di ERA5 (~28 km), che
  non risolve la pioggia convettiva locale.
- **Densità IFFI** contata entro 500 m dalla cella (non dal centroide).
- **Saturazione densità** in YAML (`static.iffi_density_saturation`),
  bilanciata su ITALICA (recall vs precisione).

Validazione su ground-truth (pioggia pluviometro reale): ~63–77% delle
frane reali raggiungono ≥Moderate; backtest end-to-end su una finestra
scatenante con hit-rate e lead-time entro i target §2.5. Il FAR resta
limitato dall'incompletezza del catalogo eventi, non dal motore.

---

## Configurazione

Caricata da variabili d'ambiente (e `.env` opzionale) via
`limen.config.settings.Settings`. I campi annidati usano `__` come
delimitatore.

| Variabile | Default | Note |
|-----------|---------|------|
| `DB__CONNECTION_STRING` | `postgresql://limen:limen@localhost:5432/limen` | DSN PostgreSQL. Aggiungi `?sslmode=require` per Neon. |
| `OBJECT_STORE__BACKEND` | `filesystem` | `filesystem` o `s3`. |
| `OBJECT_STORE__ENDPOINT_URL` | _vuoto_ | Endpoint S3-compatibile (MinIO, R2, B2). |
| `SCHEDULER__CACHE_CLEANUP` | `apscheduler` | `pg_cron` o `apscheduler`. **Usa APScheduler su Neon.** |
| `LLM__PROVIDER` | _vuoto_ | Override: `anthropic` / `openai` / `foundry` / `ollama`. |
| `LLM__OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama host (da container: `host.docker.internal`). |
| `LLM__OLLAMA_MODEL` | `qwen2.5` | Modello Ollama (es. `qwen3.6:latest`). |
| `GEOSERVER_SOURCE__DB_DSN` | _vuoto_ | DSN del PostGIS di mcp-geoserver (IFFI + PAI). |
| `LIMEN_DEM_RASTER` | _vuoto_ | GeoTIFF DTM per lo slope (opt-in). |
| `LIMEN_ITALICA_CSV` | _vuoto_ | CSV e-ITALICA locale; se assente, auto-download da Zenodo. |
| `LOG_LEVEL` / `LOG_JSON` | `INFO` / `false` | Livello + output JSON dei log structlog. |

Vedi [`.env.example`](./.env.example) per l'elenco completo con esempi.

---

## Schema database (highlights)

`aoi`, `grid_cells`, `cell_static_factors`, `iffi_landslides`,
`pai_hazard`, `landslide_events` (catalogo eventi datati),
`risk_assessments`, `norm_stats`, `raster_refs`, `app_cache`,
`alert_dispatches`, `seismic_events`, `fire_perimeters`, tabelle sensori,
`schema_migrations`. Tutte le geometrie in EPSG:4326; distanze/aree
calcolate in EPSG:3035 (LAEA Europe). Migrazioni SQL immutabili in
`src/limen/data/migrations/NNN_*.sql`.

---

## Testing e quality gates

```bash
make test                  # unit + integration (testcontainers)
make test-unit             # veloce, senza Docker
make check                 # lint + typecheck + test
make lint                  # ruff check
make format                # ruff format
make typecheck             # mypy --strict su src/ (esegui dopo `uv sync --all-groups`)
```

Gate prima di ogni commit: `ruff check` + `ruff format` puliti,
`mypy --strict` pulito, `pytest` verde. Su Apple Silicon i test di
integrazione usano automaticamente `imresamu/postgis-arm64`
(override con `LIMEN_TEST_POSTGIS_IMAGE`).

---

## Roadmap

- **Attivazione H (idraulica)** dal PostGIS di GeoServer: caricare il
  mosaico idraulica ISPRA + estendere il loader (peso 0.03, completezza).
- **Autenticazione Clerk** (`@clerk/clerk-react` sulla stessa SPA Vite +
  validazione JWT in FastAPI) — unico item deferito; vedi memoria
  `production-stack`.

---

## Attribuzione & licenze open

Limen usa i seguenti dataset aperti — l'attribuzione è obbligatoria
quando la mappa / i briefing vengono pubblicati:

* **ISPRA IdroGEO** (inventario IFFI, mosaici PAI frana e idraulica) —
  © ISPRA / Autorità italiane, CC-BY 4.0. https://idrogeo.isprambiente.it
* **e-ITALICA** (catalogo frane innescate da pioggia, CNR-IRPI) —
  CC-BY 4.0, Zenodo DOI 10.5281/zenodo.14204473.
* **Copernicus** (Open-Meteo, ERA5, **CERRA** reanalisi regionale) —
  licenza Copernicus, uso libero con attribuzione. https://open-meteo.com
* **INGV** (servizio eventi FDSN, ShakeMap) — CC-BY 4.0.
  https://terremoti.ingv.it
* **EFFIS** (perimetri aree bruciate) — termini Copernicus EFFIS.
* **ISTAT** (confini amministrativi 2023) — CC-BY 4.0.
* **OpenStreetMap** (basemap) — ODbL.

---

## Contributi & sicurezza

* [`CONTRIBUTING.md`](./CONTRIBUTING.md) — setup dev, stile commit, gate.
* [`SECURITY.md`](./SECURITY.md) — canale di disclosure privato.
* [`CHANGELOG.md`](./CHANGELOG.md) — storico versionato (Keep a Changelog).

## Licenza

Apache-2.0 — vedi [LICENSE](./LICENSE).
