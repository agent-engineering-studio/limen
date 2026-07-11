<p align="center">
  <img src="docs/images/banner.png" alt="Limen — Landslide Monitoring Framework" width="100%">
</p>

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
uv run limen report build   # report HTML statico zone a rischio → report/index.html
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
[`docs/openclaw.md`](./docs/openclaw.md),
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
| **Job periodici** | workflow MAF orario (con shadow ML), **sweep previsionale** ogni 6 h, **nowcast radar DPC** ogni 15 min, report nazionale giornaliero, sync ISPRA settimanale, **drift monitor ML** (PSI/KS training-vs-live sulle feature canoniche che lo shadow persiste), cache cleanup + retention di `model_runs` (default 30 gg) | APScheduler in-process | `api/jobs/` |
| **Radar DPC (nowcast)** | SRI nazionale 1 km / 5 min (piattaforma radar DPC, CC-BY-SA): pioggia ≥ `NOWCAST__MIN_INTENSITY_MMH` su una regione ⇒ il workflow di quella AOI parte subito invece di aspettare il tick orario (cooldown 45 min; alert dal percorso operativo normale) | poll ogni `NOWCAST__INTERVAL_MINUTES` | `integrations/dpc/` + `api/jobs/nowcast_monitoring.py` |
| **Forecast previsionale** | scoring a `now+H` ore con pioggia prevista Open-Meteo (osservata+prevista nella stessa finestra); champion + challenger ML sulle stesse celle; report on-demand o alert "PREVISIONE" schedulato con dedup (AOI, orizzonte) | `limen forecast` / job ogni `FORECAST__INTERVAL_HOURS` | `agents/workflows/forecast.py` + `api/jobs/forecast_monitoring.py` |
| **MCP `limen-ops`** | `tool_risk_summary`, `tool_top_risk_cells`, `tool_cell_breakdown`, `tool_recent_alerts`, `tool_national_report`, `tool_run_monitor` (admin, fail-closed su `MCP_ADMIN_TOKEN`) per gateway agentici (OpenClaw, Claude Desktop) | servizio compose `mcp`, HTTP `127.0.0.1:8766/mcp` | `mcp/` + `limen mcp-serve` |
| **Report nazionale giornaliero** | quadro aggregato 20 regioni (riepilogo per regione, top celle nazionali, top ML shadow, conteggi alert 24h) reso in italiano deterministico e spedito ogni mattina sui canali di notifica | cron `REPORT__HOUR_UTC` (default 06 UTC) | `api/jobs/daily_report.py` + `tool_national_report` |
| **Report HTML statico** | pagina autosufficiente delle *zone a maggior rischio*: cluster di celle contigue (PostGIS `ST_ClusterDBSCAN`), snapshot mappa per cluster (basemap OSM/Carto + celle colorate, fallback SVG offline), motivo deterministico S/M/E/F/H + verdetto, palette YlOrRd. Nessun LLM. Prova la soglia di allerta (`High`) e, se **nessuna** zona la supera, scende (`Moderate`→`Low`) mostrando comunque le aree relativamente più a rischio con un banner informativo (nessun allarme) — il report non è mai vuoto. **Archivio immutabile versionato** (`report/archive/<ts>/` + `manifest.json`) per fact-checking futuro; idempotente (salta il rebuild se l'assessment non cambia); pubblicabile via GitHub Pages (`REPORT__HTML_PUBLISH`) | al boot + ogni `REPORT__HTML_INTERVAL_HOURS` (default 1h) o on-demand | `report/` + `limen report build` + `api/jobs/html_report.py` |
| **Vector tiles** | matview `mv_latest_risk` (grid_cells ⨝ ultimo risk_assessment per cella), rinfrescata da `refresh_mv_latest_risk()`; servita da **pg_tileserv** | per ciclo di monitoraggio | migrazione `007_map_views.sql` |
| **Frontend** | SPA Vite + TS + React + **MapLibre GL JS**: `RiskMap` (vector tiles, palette 5 classi ColorBrewer YlOrRd), `LegendPanel` (etichette + range, non solo colore), `AlertList`, `CellPopup`, `TimelineSlider`; overlay PMTiles PAI/IFFI opt-in | pubblico, read-only | `frontend/` |
| **Notifiche** | Protocol `NotificationChannel` + Telegram / MQTT / Email / **Webhook** (POST JSON a gateway agentici, es. OpenClaw `/hooks` con bearer token); dispatcher in parallelo con isolamento eccezioni per canale; dedup su `alert_dispatches` | per tick del workflow | `notifications/` |

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
| `LLM__OLLAMA_MODEL` | `qwen3.6:latest` | Modello Ollama unico per tutti i ruoli agente. |
| `SCORING__MODE` | `champion_only` | `shadow` fa girare il challenger ML in parallelo (scrive solo `model_runs`). |
| `FORECAST__ENABLED` | `true` | Sweep previsionale schedulato; `FORECAST__HORIZON_HOURS` (48), `__INTERVAL_HOURS` (6), `__MIN_LEVEL` (High). |
| `REPORT__HTML_ENABLED` | `true` | Report HTML statico; `__HTML_INTERVAL_HOURS` (1), `__HTML_RUN_AT_STARTUP` (true), `__HTML_OUTPUT_DIR` (report), `__HTML_MIN_LEVEL` (High), `__HTML_MAX_CLUSTERS` (50), `__HTML_ARCHIVE_KEEP` (240), `__HTML_PUBLISH` (false). |
| `NOTIFICATIONS__WEBHOOK__URL` | _vuoto_ | Gateway agentico (OpenClaw `/hooks`); `__TOKEN` per il bearer. |
| `MCP_ADMIN_TOKEN` | _vuoto_ | Abilita `tool_run_monitor` sull'MCP; assente = disabilitato (fail-closed). |
| `GEOSERVER_SOURCE__DB_DSN` | _vuoto_ | DSN del PostGIS di mcp-geoserver (IFFI + PAI). |
| `LIMEN_DEM_RASTER` | _vuoto_ | GeoTIFF DTM per lo slope (opt-in). |
| `LIMEN_ITALICA_CSV` | _vuoto_ | CSV e-ITALICA locale; se assente, auto-download da Zenodo. |
| `LOG_LEVEL` / `LOG_JSON` | `INFO` / `false` | Livello + output JSON dei log structlog. |

Vedi [`.env.example`](./.env.example) per l'elenco completo con esempi.

---

## Schema database (highlights)

`aoi`, `grid_cells`, `cell_static_factors`, `iffi_landslides`,
`pai_hazard`, `landslide_events` (catalogo eventi datati),
`risk_assessments`, `model_runs` (predizioni del challenger in shadow),
`training_samples` (feature store ML), `norm_stats`, `raster_refs`,
`app_cache`, `alert_dispatches`, `forecast_dispatches` (dedup alert
previsionali), `seismic_events`, `fire_perimeters`, tabelle sensori,
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

## Stato & roadmap

Completati di recente:

- **Copertura nazionale** (20 regioni ISTAT) con soglia Caine ri-tarata su
  e-ITALICA e pioggia di backtest CERRA.
- **Componente H (idraulica)** attivo dal mosaico idraulica ISPRA via
  GeoServer (~132k celle in zona di pericolosità idraulica).
- **Autenticazione Clerk** attiva: sign-in sulla SPA Vite (`@clerk/react`) +
  validazione JWT sugli endpoint protetti FastAPI (`CLERK__ENABLED`).
- **Sfidante ML addestrato** su 37k campioni (frane e-ITALICA + pioggia
  antecedente CERRA per campione): **AUC-PR 0.60 vs 0.28 del motore
  deterministico** sulla stessa partizione spaziale e la stessa pioggia
  (`limen train`; registro MLflow; promozione solo manuale). Backup/ripristino
  del dataset e del modello: `make dump-training` / `make restore-training`.
- **Shadow mode attivo**: il challenger ML gira in parallelo al champion
  a ogni ciclo orario (`SCORING__MODE=shadow`) e scrive le probabilità in
  `model_runs`; il motore deterministico resta l'unico autoritativo.
- **`limen forecast`** — run *previsionale* a `now+H` ore: la finestra
  Open-Meteo miscela pioggia osservata e prevista, champion e ML valutano
  le stesse celle, report in `./reports/` senza toccare lo stato operativo
  (`LIMEN_FORECAST_AOI` / `_HOURS` / `_CELL_LIMIT`).
- **MCP `limen-ops`** (`limen mcp-serve`): rischio, allerte e run del
  workflow esposti come tool per gateway agentici (OpenClaw, Claude Desktop).
  Nel compose è il servizio `mcp` (immagine `limen/mcp:0.1`, HTTP su
  `127.0.0.1:8766`; `LIMEN_MCP_BIND=0.0.0.0` solo dietro TLS quando il
  gateway sta su un'altra macchina). Aggancio OpenClaw:
  `openclaw mcp set limen-ops '{"url":"http://127.0.0.1:8766/mcp","transport":"streamable-http"}'`.
- **Canale di notifica `webhook`**: gli alert POSTano il payload JSON al
  gateway agentico (es. OpenClaw `/hooks`, bearer token) — pull via MCP per
  le domande, push via webhook per gli eventi. Config:
  `NOTIFICATIONS__ENABLED_CHANNELS=["webhook"]` + `NOTIFICATIONS__WEBHOOK__URL/TOKEN`.
- **Pagina divulgativa** «Come funziona» nel frontend (`#/come-funziona`)
  con simulatore che usa la formula reale di produzione.
- **Cartella `llm-training/`**: dataset (assessment → briefing) in formato
  Alpaca + guida passo-passo per l'eventuale fine-tuning con LLaMA-Factory.

- **Pipeline event-driven** (attiva di default, opt-out `FORECAST__ENABLED=false`): sweep previsionale
  schedulato a `now+48h` con pioggia prevista; celle a livello ≥
  `FORECAST__MIN_LEVEL` fanno partire un alert **previsionale** sugli stessi
  canali (webhook/OpenClaw, Telegram…), etichettato "PREVISIONE", riassunto
  deterministico, dedup per (AOI, orizzonte) separata dagli alert operativi.

- **Nowcast radar DPC** (attivo di default): l'SRI a 1 km della rete radar
  nazionale fa da innesco a orizzonte breve — pioggia intensa vista dal
  radar ⇒ scoring immediato della regione colpita.

Prossimi passi:

- **Confronto shadow** challenger vs champion su eventi reali (dopo qualche
  settimana di `model_runs` accumulati).

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
* **CORINE Land Cover 2018 Italia** (SINAnet/ISPRA) — CC-BY.
  https://groupware.sinanet.isprambiente.it
* **Carta Geolitologica d'Italia 1:500k** (Geoportale Nazionale
  PCN/MASE, Servizio Geologico d'Italia) — CC-BY 4.0.
* **ISTAT** (confini amministrativi 2023) — CC-BY 4.0.
* **OpenStreetMap** (basemap) — ODbL.

---

## Contributi & sicurezza

* [`CONTRIBUTING.md`](./CONTRIBUTING.md) — setup dev, stile commit, gate.
* [`SECURITY.md`](./SECURITY.md) — canale di disclosure privato.
* [`CHANGELOG.md`](./CHANGELOG.md) — storico versionato (Keep a Changelog).

## Licenza

Apache-2.0 — vedi [LICENSE](./LICENSE).
