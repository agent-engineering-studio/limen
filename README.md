<h1 align="center">Limen</h1>

<p align="center">
  <b>Where in Italy could the ground slide, the water rise or the woods burn, right now and in the next 72 hours?</b><br>
  An open, explainable early-warning map for <b>landslides, floods and wildfires</b>, one square kilometre at a time.
</p>

<p align="center">
  🗺️ <a href="https://limen.agentengineering.it/?lang=en"><b>Open the live map</b></a> ·
  📖 <a href="#how-it-works">How it works</a> ·
  🚀 <a href="#quick-start-run-it-on-your-laptop">Quick start</a> ·
  🛰️ <a href="#the-data-every-source-and-its-licence">Data sources</a> ·
  🧩 <a href="#the-companion-libraries">Libraries</a> ·
  ☕ <a href="#support-limen">Support</a>
</p>

<p align="center">
  🇬🇧 <b>English</b> · 🇮🇹 <a href="./README.it.md">Italiano</a>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.12+-blue.svg" alt="Python 3.12+"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-EUPL--1.2-green.svg" alt="License: EUPL-1.2"></a>
  <a href="https://github.com/astral-sh/uv"><img src="https://img.shields.io/badge/managed%20by-uv-261230" alt="uv"></a>
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/badge/lint-ruff-261230" alt="ruff"></a>
  <a href="http://mypy-lang.org/"><img src="https://img.shields.io/badge/typed-mypy%20--strict-blue" alt="mypy --strict"></a>
  <img src="https://img.shields.io/badge/data-100%25%20open-orange" alt="Open data only">
  <img src="https://img.shields.io/badge/cloud-none%20(self--hosted)-lightgrey" alt="Self-hosted, no cloud provider">
</p>

<p align="center">
  <a href="https://limen.agentengineering.it/?lang=en"><img src="docs/images/screenshots/home.webp" alt="Limen home page: 'Territorial risk, cell by cell' — 312,550 cells monitored, 20 regions, updated every hour, 1 km² grid" width="100%"></a>
</p>

---

## Contents

- [Limen in one minute](#limen-in-one-minute)
- [What you see on the map](#what-you-see-on-the-map)
- [How it works](#how-it-works)
- [Quick start: run it on your laptop](#quick-start-run-it-on-your-laptop)
- [Configuration: the `.env` file, step by step](#configuration-the-env-file-step-by-step)
- [The data: every source and its licence](#the-data-every-source-and-its-licence)
- [The companion libraries](#the-companion-libraries)
- [Architecture](#architecture)
- [Does it work? What we measured](#does-it-work-what-we-measured)
- [Installing on a server](#installing-on-a-server)
- [Backup and restore](#backup-and-restore)
- [Testing and quality gates](#testing-and-quality-gates)
- [Status and roadmap](#status-and-roadmap)
- [Licences and attribution](#licences-and-attribution)
- [Support Limen](#support-limen) · [Contributing](#contributing-and-governance)

---

## Limen in one minute

Italy has more than **721,000 mapped landslides**, about **6.8 million
people** living where rivers can flood, and every summer brings wildfires.
The official warnings of the Civil Protection give **one colour per zone**, a
zone being dozens of municipalities, for today and tomorrow.

**Limen** (Latin for *threshold*) looks closer. It splits the whole country
into **312,550 squares of 1 km²** and, **every hour**, asks each of them three
questions:

| | Hazard | The question, in plain words | What raises the danger |
|---|---|---|---|
| 🟣 | **Landslide** | *Is this slope fragile, and is it getting too much rain?* | steep ground, past landslides, clay soils × rain above the level that triggered landslides before, plus recent earthquakes and burnt slopes |
| 🔵 | **Flood** | *Can water reach this place, and is it coming?* | ground the flood maps already mark as floodable × heavy rain (forecast **and** already fallen) or a river running well above its ordinary high flow |
| 🩷 | **Wildfire** | *Would a fire catch and spread here today?* | the Canadian Fire Weather Index (dryness, wind, heat) × the fuel on the ground and the slope |

Each answer is a **score from 0 to 1**, shown in **five classes**
(none · low · moderate · high · very high) on a public map, with a
**72-hour forecast** and **alerts** when a cell crosses a threshold.

Three things make Limen different:

1. **Every number can be explained.** The score comes from a written-down
   formula, not a black box. Click a cell and you see which ingredient pushed
   it up: the rain, the slope, the river.
2. **AI writes words, never numbers.** A language model turns the result
   into a short summary per region. It cannot change a score; a test enforces
   it.
3. **Open all the way down.** Open data only, open code (EUPL-1.2),
   self-hosted on one server, no cloud provider, no login, no tracking.

> [!IMPORTANT]
> Limen is a **decision-support tool**. Its outputs are modelled indicators,
> **not official Civil Protection warnings**. It works *alongside* the
> official bulletin: the bulletin says *which zone*; Limen tries to say
> *where inside it, why, and what comes next*.

**Not a developer?** The plain-language pages in
[`docs/divulgazione/`](./docs/divulgazione/README.md) (Italian) and the
**How it works** page on the [live site](https://limen.agentengineering.it/?lang=en#/come-funziona)
explain everything without jargon.

---

## What you see on the map

<table>
<tr>
<td width="50%"><a href="https://limen.agentengineering.it/?lang=en#/dashboard"><img src="docs/images/screenshots/dashboard-italy.webp" alt="Dashboard: the whole of Italy coloured by estimated hazard, with counts of high-class areas per hazard and a 72-hour timeline"></a></td>
<td width="50%"><a href="https://limen.agentengineering.it/?lang=en#/dashboard"><img src="docs/images/screenshots/dashboard-cells.webp" alt="Zoomed into Puglia: individual 1 km cells, with flood cells along the rivers of the Tavoliere in red and the municipalities outlined"></a></td>
</tr>
<tr>
<td><b>The whole country.</b> Pick a hazard (or all of them), see how many
areas are in the high class, and drag the timeline to <b>+24, +48, +72
hours</b>.</td>
<td><b>Zoom in and the regions become cells.</b> Here the plain of Foggia
(Puglia): the flood-prone strips along the rivers light up, cell by cell.
Each cell opens a breakdown of its score.</td>
</tr>
<tr>
<td colspan="2"><a href="https://limen.agentengineering.it/?lang=en#/regioni"><img src="docs/images/screenshots/regions-to-watch.webp" alt="Regions to watch: regions ordered by estimated hazard, the official warning on each row, and a short AI-written summary per hazard"></a></td>
</tr>
<tr>
<td colspan="2"><b>Regions to watch.</b> Regions ranked by the numbers, with
the official warning beside them and a short summary written by Claude for
each hazard. The summary explains; the ranking and the colours come only from
the formulas. The report downloads as a PDF.</td>
</tr>
</table>

Other pages on the live site: **Checks** (`#/verifiche`, news of real events
compared with what Limen had forecast before them), **Integrations**
(`#/integrazioni`, the APIs for other software and AI agents), **Sensors**
(`#/sensori`, an open network of in-situ sensors), **Sources**
(`#/fonti`), and **ML diagnostics** (`#/diagnostica-ml`).

---

## How it works

<p align="center">
  <img src="docs/images/how-it-works.svg" alt="How Limen works: 1 read open data (weather, radar, rivers, ground maps, satellites, earthquakes); 2 place it on 312,550 cells of 1 km²; 3 score with three readable formulas for landslide, flood and wildfire, 0 to 1 in five classes; 4 share on a public map, alerts, AI summaries and open APIs. Rhythm: every hour, 4 times a day for the 72-hour forecast, every 15–45 minutes on radar rain or satellite fires, every night for ML checks and backups." width="100%">
</p>

**1 · Read.** Limen pulls public data: the weather forecast and archive, the
national rain radar, river discharge, maps of past landslides and of
flood-prone areas, terrain, land cover, satellite fire detections, ground
motion from radar satellites, earthquakes. [All sources are listed below](#the-data-every-source-and-its-licence),
with their licences.

**2 · Place.** Everything is brought onto the same grid of 1 km² cells.
Things that do not change (slope, soil, the flood maps) are computed once per
cell. Things that change (rain, rivers, fire weather) are read every hour, on
a lattice of weather points, and each cell reads its nearest point.

**3 · Score.** One formula per hazard, with every weight and threshold in a
YAML file you can read ([`src/limen/config/hazards/`](./src/limen/config/hazards/)):

```text
landslide = weighted mix of  terrain (S) · rain vs. Caine's threshold (M) · earthquakes (E)
                             · recent fires (F) · water in rivers and soil (H) · ground motion (K)
flood     = susceptibility × max( pluvial trigger , fluvial trigger )
wildfire  = fire-weather index × ( base + fuel + slope )
```

Two design choices protect against false calm:

- **Maximum, not sum.** For floods, rain and rivers are two ways for the same
  place to end up under water: Limen takes the stronger, so two moderate
  signals cannot invent a severe one.
- **"Not measured" is not "no danger".** If a data source is down, the
  affected cells are drawn **grey**, like unassessed cells, never in the
  "calm" colour. A zero that only means *we don't know* would be the one
  error that reassures people wrongly.

**4 · Share.** The result goes to the map, to alerts (Telegram, e-mail, MQTT,
webhook), to regional summaries written by an AI that **never changes a
number**, and to open APIs (REST, MCP for AI agents, A2A).

<details>
<summary><b>The workflow step by step</b> (for developers)</summary>

Each run is a chain of small steps ("executors") of a Multi-Agent Framework:

```mermaid
flowchart LR
    A[AreaResolver<br/>which cells] --> B[StaticFactors<br/>slope, soil, maps]
    B --> C[MeteoFetch<br/>rain, soil moisture]
    C --> D[SeismicCheck<br/>INGV]
    D --> E[FireCheck<br/>EFFIS, FIRMS]
    E --> F[SensorFetch<br/>optional IoT]
    F --> G[RiskScoring<br/>pure formula]
    G --> H[EscalationGate]
    H --> I[PersistResult<br/>PostGIS]
    I --> J[AlertDispatch<br/>dedup + channels]
```

Flood runs add `FloodForecastFetch` (rain forecast + GloFAS rivers) and
`ObservedRain` (DPC radar-gauge «Merging»); wildfire runs add `FwiUpdate`
(the Fire Weather Index chain, one per weather node). The scoring engine is a
**pure function**: no database, no network, no AI.

</details>

---

## Quick start: run it on your laptop

**You need:** [Docker](https://docs.docker.com/get-docker/) with Compose,
[`uv`](https://docs.astral.sh/uv/getting-started/installation/) (it installs
Python 3.12 for you), `make`, and Node 22 for the map frontend. About 10 GB of
free disk for a regional demo; no API key at all.

```bash
git clone https://github.com/agent-engineering-studio/limen.git
cd limen
cp .env.example .env               # works as is for a local demo
uv sync --all-groups               # install Python dependencies (Intel Mac: see below)
make up                            # start Postgres + PostGIS, GeoServer, map server, frontend
make init                          # build the data (see below) — safe to re-run
uv run limen serve                 # API on http://localhost:8080/docs
( cd frontend && npm ci && npm run dev )   # map on http://localhost:5173
```

On macOS, `make` must be GNU make ≥ 4.3 and an Intel Mac cannot install the
ML groups: see [Pitfalls met on a real install](#pitfalls-met-on-a-real-install-macos-host).

What `make init` does, in order (every step is idempotent, so you can stop
and restart it):

```mermaid
flowchart LR
    M[migrate<br/>create tables] --> S[seed<br/>20 regions,<br/>1 km² grid]
    S --> I[ingest-events<br/>e-ITALICA<br/>landslide catalogue]
    I --> D[static data<br/>download ISPRA, ISTAT,<br/>CORINE, geology, DTM]
    D --> B[per-cell factors<br/>slope, past landslides,<br/>flood maps, fuel]
    B --> C[calibrate<br/>per-region<br/>normalisation]
```

The static-data step (`scripts/load_static_data.sh`, the same path for
`make up`, `make init` and `make static-data`) **downloads on its own**
everything that needs no account: the IFFI landslide inventory and the PAI
hazard mosaics from IdroGEO (`limen geodati-sync`, via
[ispra-idrogeo](#ispra-idrogeo)), the ISTAT borders, CORINE 2018, the
1:500k geology and the 5 m DTM (IRPI-CNR HR-DTM, Zenodo). It loads them into
the [mcp-geo-server](#mcp-geo-server) PostGIS, adds EFFIS burnt areas and,
with a key, EGMS ground motion, then computes the per-cell factors. The first
full run for Italy is ~25 GB (the DTM included); later runs skip whatever has
not changed.

One more ISPRA dataset arrives through the night instead: the **exposure per
municipality**. The nightly `esposizione_ispra` step stores in
`esposizione_comuni` how many residents of each municipality live in PAI
landslide hazard P3+P4 and flood hazard P2 areas (ISTAT 2021 census), plus
buildings and businesses, from the IdroGEO API. The answers are kept under
`LIMEN_DATA_DIR/idrogeo` and asked for again only after 30 days, so most
nights read them from disk in ~2 s. `/api/comuni` returns them as
`esposizione_ispra`; they enter no score. `limen esposizione-sync` fills the
table at once.

Then run one scoring pass and look at the map:

```bash
LIMEN_MONITOR_AOI=it-puglia uv run limen monitor-once   # score one region now
uv run limen data-status                                # which data layers are loaded
uv run limen report build                               # static HTML report → site/index.html
```

> [!TIP]
> Seeding all twenty regions makes ~312,000 cells and takes a while. For a
> first look, follow [`docs/demo.md`](./docs/demo.md), which runs on a small
> area in a few minutes.

**On Neon (serverless Postgres, dev/test only):** set
`DB__CONNECTION_STRING=...?sslmode=require` and
`SCHEDULER__CACHE_CLEANUP=apscheduler`; nothing else changes.

---

## Configuration: the `.env` file, step by step

Everything is configured with environment variables, usually in a `.env`
file at the repository root. [`.env.example`](./.env.example) lists every
variable with comments: copy it and change only what you need.

**One rule to read it:** a double underscore means "section → field".
`FIRMS__MAP_KEY` is the `map_key` field of the `firms` section; the settings
are typed and validated at start-up by
[`limen.config.settings`](./src/limen/config/settings.py).

Limen is built to **start with zero keys** and get richer as you add them.
Every external source is *fail-closed*: without its key, that feed stays off
(and says so in the logs), the rest keeps working.

```mermaid
flowchart LR
    L0["<b>Level 0 · no keys</b><br/>public Open-Meteo weather, DPC radar,<br/>INGV quakes, EFFIS burnt areas,<br/>FIRMS archive, Copernicus EMS floods,<br/>e-ITALICA landslides"]
    L1["<b>Level 1 · static layers</b><br/>make static-data → ISPRA, ISTAT,<br/>CORINE, geology, DTM, no keys<br/>imperviousness, OSM: make fetch-static"]
    L2["<b>Level 2 · free keys</b><br/>FIRMS__MAP_KEY → live satellite fires<br/>COPERNICUS__EWDS_KEY → GloFAS rivers<br/>EGMS__SERVICE_KEY → ground motion"]
    L3["<b>Level 3 · production</b><br/>OPENMETEO__FORECAST_URL → own weather server<br/>LLM gateway + ANTHROPIC_API_KEY → summaries<br/>NOTIFICATIONS__* → alerts · BACKUP__* → backups"]
    L0 --> L1 --> L2 --> L3
```

### The keys that unlock more data

All of these are **free**. None is needed to start.

| Variable | What it switches on | Where to get it | Without it |
|---|---|---|---|
| `LIMEN_GEOSERVER=1` | the [mcp-geo-server](#mcp-geo-server) stack: GeoServer, its PostGIS, web UI and geo MCP servers, for the PAI/IFFI WMS overlays (~2 GB of RAM). The numbers do not need it: the ISPRA and ISTAT vectors are loaded into Limen's own database by `limen carica-vettori` | nothing to get | no WMS overlays (PMTiles ones still work) |
| `LIMEN_AGENTI=1` | the `limen-ops` MCP server for AI agents (OpenClaw & co.) | nothing to get | no MCP for agents |
| `LIMEN_DEM_RASTER` | use your own terrain model (e.g. TINITALY 10 m) instead of the HR-DTM 5 m downloaded at init | a GeoTIFF on disk ([`data/README.md`](./data/README.md)) | the downloaded HR-DTM is used |
| `FIRMS__MAP_KEY` | live NASA satellite fire detections every 45 min; a fire can start a run within hours | [firms.modaps.eosdis.nasa.gov/api/map_key](https://firms.modaps.eosdis.nasa.gov/api/map_key/) | only the yearly archive (no key needed) |
| `COPERNICUS__EWDS_KEY` | river discharge forecast and each river's *ordinary high flow* from Copernicus GloFAS | ECMWF account on [ewds.climate.copernicus.eu](https://ewds.climate.copernicus.eu/how-to-api); accept the CEMS-Floods licence once | GloFAS via the public Open-Meteo API |
| `EGMS__SERVICE_KEY` (or `__SERVICE_KEY_FILE`) | ground-motion velocities from Sentinel-1 (EGMS), feeding the ML features | [land.copernicus.eu](https://land.copernicus.eu) → profile → *API Tokens* (the JSON is shown once) | no ground-motion features |
| `OPENMETEO__FORECAST_URL` / `__ARCHIVE_URL` | your own Open-Meteo server (`make meteo-up`); the public API's 10,000 calls/day are not enough for all of Italy | self-hosted, compose profile `meteo` | public API (fine for one region) |
| `ANTHROPIC_API_KEY` | regional summaries with Claude, under a monthly cap (`LLM__ANTHROPIC_BUDGET_MENSILE_USD`, default 10 $) | [console.anthropic.com](https://console.anthropic.com) | local model via llama.cpp, or a deterministic text |
| `NOTIFICATIONS__*` | alerts on Telegram, e-mail, MQTT or a webhook (`NOTIFICATIONS__ENABLED_CHANNELS`) | your bot / SMTP / broker | alerts stay in the database and on the map |
| `MCP_ADMIN_TOKEN` | admin tools on the MCP server (start a sweep, build a report) | any long random string | admin tools disabled |

### The variables you will touch most

| Variable | Default | What it does |
|---|---|---|
| `LIMEN_DATA_ROOT` | the repo's `data/` | **One folder for all the data** of a deployment: datasets, reports, models, GeoServer data, OSM, radar. Moving Limen = copying this folder and changing this line. Must be absolute when set. |
| `DB__CONNECTION_STRING` | `postgresql://limen:limen@localhost:5432/limen` | PostgreSQL 16 + PostGIS. Add `?sslmode=require` for Neon. |
| `OBJECT_STORE__BACKEND` | `filesystem` | `filesystem` or `s3` (any S3-compatible store: MinIO, R2, B2, via `OBJECT_STORE__ENDPOINT_URL`). |
| `SCHEDULER__ENABLED` | `true` | Periodic jobs run in the `limen worker` process; set `false` in the API container. |
| `SCHEDULER__FORECAST_CELLS_HOURS_UTC` | `[2, 8, 14, 20]` | When the 72-hour per-cell forecast is recomputed. |
| `LLM__PROVIDER` | _empty_ | Force `anthropic` / `openai` / `foundry` / `ollama` / `llamacpp`. Empty: a cloud key wins, otherwise llama.cpp. |
| `LLM__LLAMACPP_BASE_URL` | `http://127.0.0.1:8091` | The LiteLLM inference gateway (not `:8081`, which is GeoServer). From a container: `host.docker.internal`. |
| `SCORING__MODE` | `champion_only` | `shadow` also runs the ML challenger at night, writing only to `model_runs`. |
| `FORECAST__ENABLED` | `true` | Predictive sweep and "FORECAST" alerts. |
| `NOWCAST__*` | on | DPC radar trigger: heavy rain seen by radar starts a run at once. |
| `LOG_LEVEL` / `LOG_JSON` | `INFO` / `false` | Structured logs. |

<details>
<summary><b>More variables</b> (reports, LLM roles, ports, images)</summary>

| Variable | Default | Notes |
|-----------|---------|------|
| `SCHEDULER__CACHE_CLEANUP` | `apscheduler` | `pg_cron` or `apscheduler`. **Use APScheduler on Neon.** |
| `EGMS__CARTELLA` | `data/egms` | EGMS tiles, kept between syncs (Docker: the `LIMEN_EGMS_DIR` volume on `/var/lib/limen/egms`). |
| `LLM__MODELS__<ROLE>` | Claude id | Role → model map. `LLM__MODELS__FEDELTA` is a Claude id sent as a Message Batch. See [`docs/inference.md`](./docs/inference.md). |
| `LLM__LLAMACPP_TIMEOUT_SECONDS` | `120` | Ceiling for roles without an override; `LLM__LLAMACPP_ROLE_TIMEOUT_SECONDS` (JSON) per role. |
| `LLM__OLLAMA_BASE_URL` / `LLM__OLLAMA_MODEL` | `http://localhost:11434` / `qwen3.6:latest` | Ollama host and model (needs `LLM__PROVIDER=ollama`). |
| `REPORT__HTML_ENABLED` | `true` | Static HTML report; `__HTML_INTERVAL_HOURS` (1), `__HTML_MIN_LEVEL` (High), `__HTML_PUBLISH` (false). |
| `NOTIFICATIONS__WEBHOOK__URL` / `__TOKEN` | _empty_ | Agent gateway (e.g. OpenClaw `/hooks`) and bearer token. |
| `LIMEN_ITALICA_CSV` | _empty_ | Local e-ITALICA CSV; if absent, auto-download from Zenodo. |
| `LIMEN_IMAGE_PREFIX` / `LIMEN_IMAGE_TAG` | _empty_ | Pull images from GHCR instead of building them ([below](#images-built-here-or-pulled-from-ghcr)). |
| `LIMEN_DOMINIO` | _empty_ | Your domain: `make up` adds Caddy with Let's Encrypt certificates. |
| `BACKUP__*` | _empty_ | S3-compatible bucket for the nightly backup ([below](#backup-and-restore)). |
| `LIMEN_*_BIND` | `127.0.0.1` | Bind address of every published port ([below](#published-ports-docker-bypasses-ufw)). |

The full list, with comments, is in [`.env.example`](./.env.example).

</details>

---

## The data: every source and its licence

Limen uses **only open data**. This is what it reads, what for, and under
which terms.

| Source | 🟣 Landslide | 🔵 Flood | 🩷 Wildfire |
|---|:---:|:---:|:---:|
| **Weather & water** | | | |
| Open-Meteo (forecast + archive) | ● rain, soil moisture | ● rain | ● heat, humidity, wind, rain |
| DPC rain radar | ○ trigger | ● rain already fallen | |
| Copernicus GloFAS | ○ river term | ● river discharge | |
| **Ground** | | | |
| ISPRA IFFI + PAI | ● past landslides, hazard | ● flood hazard map | |
| Terrain model (DTM) | ● slope | | ● slope |
| CORINE · geology · imperviousness · OSM | ● rock type | ● sealed soil | ● fuel, homes nearby |
| Copernicus EGMS | ○ ground motion (ML) | | |
| **Events** | | | |
| INGV earthquakes | ● recent quakes | | |
| NASA FIRMS fires | ● burnt slopes | | ● fire history, trigger |
| EFFIS burnt areas | | | ✓ truth set |
| Copernicus EMS flooded areas | | ✓ truth set | |
| e-ITALICA dated landslides | ✓ truth set | | |

● feeds the score · ○ secondary or optional input · ✓ ground truth: past
events used to calibrate and test the formulas, not to compute today's
score.

| Source | What Limen takes | Used for | Licence | Key? |
|---|---|---|---|---|
| [**Open-Meteo**](https://open-meteo.com) (ECMWF IFS, ICON-EU, ERA5, ERA5-Land) | hourly rain, soil moisture, temperature, humidity, wind; forecast and archive | all three hazards | CC-BY 4.0 (data: Copernicus / DWD / ECMWF) | no |
| [**DPC radar platform**](https://radar.protezionecivile.it) | national SRI (1 km, 5 min) and «Merging» radar + rain-gauge accumulations | nowcast trigger; rain already fallen for floods | CC-BY-SA 4.0 | no |
| [**Copernicus EMS — GloFAS**](https://ewds.climate.copernicus.eu) | river discharge forecast per node; each node's ordinary high flow from the multi-year history | flood (fluvial branch) | CEMS-Floods licence, attribution required | free EWDS key (or via Open-Meteo) |
| [**ISPRA IdroGEO**](https://idrogeo.isprambiente.it) | IFFI landslide inventory (721,365 landslides), PAI landslide and hydraulic hazard mosaics | landslide terrain; flood susceptibility | IFFI CC-BY 4.0; mosaics CC BY-SA 4.0 | no |
| **HR-DTM 5 m** (IRPI-CNR, Zenodo) or **TINITALY 10 m** (INGV) | elevation → slope, aspect, curvature | landslide, wildfire | CC-BY 4.0 | no |
| [**CORINE Land Cover 2018**](https://groupware.sinanet.isprambiente.it) (SINAnet/ISPRA) | land cover → fuel type | wildfire | CC-BY | no |
| **Geolithological Map of Italy 1:500k** (PCN/MASE) | rock and soil type | landslide | CC-BY 4.0 | no |
| [**Copernicus Land — imperviousness**](https://land.copernicus.eu) | sealed soil (%) | flood (urban runoff) | Copernicus Land open licence | no |
| [**OpenStreetMap**](https://www.openstreetmap.org) | roads, railways; basemap | exposure; map | ODbL | no |
| [**Copernicus Land — EGMS**](https://egms.land.copernicus.eu) | ground velocity from Sentinel-1 InSAR (Ortho L3, 100 m) | ML features (not yet the map) | Copernicus Land open licence | free CLMS service key |
| [**INGV**](https://terremoti.ingv.it) | earthquakes (FDSN), ShakeMap | landslide (seismic term) | CC-BY 4.0 | no |
| [**NASA FIRMS**](https://firms.modaps.eosdis.nasa.gov) | active fires (VIIRS 375 m, MODIS 1 km), archive since 2000 | wildfire history; post-fire landslide term; fire trigger | NASA open data, acknowledgement | free MAP_KEY (live only) |
| [**EFFIS**](https://effis.jrc.ec.europa.eu) | burnt-area perimeters; official FWI | wildfire truth set and comparison | Copernicus EFFIS terms | no |
| [**Copernicus EMS Rapid Mapping**](https://rapidmapping.emergency.copernicus.eu) | observed flooded areas + where the satellite looked | flood truth set | © EU, free with attribution | no |
| [**e-ITALICA**](https://doi.org/10.5281/zenodo.14204473) (CNR-IRPI) | dated, rainfall-triggered landslides across Italy | landslide calibration and backtest | CC-BY 4.0 | no |
| **ISTAT** | municipal, provincial, regional borders (2023) | grid, rankings per comune | CC-BY | no |

Where each source is configured, refreshed and stored on disk is in
[`data/README.md`](./data/README.md); the Italian guide
[`docs/divulgazione/04-fonti-dati-open.md`](./docs/divulgazione/04-fonti-dati-open.md)
tells the same story for a general audience.

---

## The companion libraries

Some of the hardest work in Limen was **talking to the data sources**:
undocumented formats, services that answer zero instead of an error, a
steelworks that looks like a wildfire from space. We extracted that work into
**small, typed, open-source Python libraries** that anyone can use, with or
without Limen.

```mermaid
flowchart TB
    subgraph PyPI["On PyPI · Apache-2.0"]
        CEMS["copernicus-ems<br/>flooded areas"]
        EG["egms-client<br/>ground motion"]
        FC["firms-client<br/>active fires"]
        ID["ispra-idrogeo<br/>landslides & hazard maps<br/>+ idrogeo-mcp"]
        FWI["fwi-chain<br/>Fire Weather Index"]
        EF["effis-client<br/>burnt areas, official FWI"]
        RT["rainfall-thresholds<br/>rain that triggers landslides"]
        IS["imageserver-export<br/>sealed soil & land cover"]
        DR["dpc-radar<br/>national weather radar"]
    end
    MGS["mcp-geo-server · MIT<br/>GeoServer + PostGIS + MCP agent"]
    L["<b>Limen</b>"]
    CEMS --> L
    EG --> L
    FC --> L
    FWI --> L
    EF --> L
    RT --> L
    ID --> L
    IS --> L
    DR --> L
    MGS -- "ISPRA layers in PostGIS<br/>WMS map overlays" --> L
```

Limen pins each with `~=`, so a minor version needs a deliberate bump, and
uses them only for their **pure** parts (request building, parsing,
validation): network calls go through Limen's own shared client and retry
policy (`limen.integrations._http`), and the "neutral result on failure"
rule stays in Limen. The numbers that tune a hazard stay in
`src/limen/config/hazards/*.yaml`, never in a library's constants.

| Package | Pin in Limen | Licence |
|---|---|---|
| [`copernicus-ems`](https://pypi.org/project/copernicus-ems/) | `~=0.7.1` | Apache-2.0 |
| [`egms-client`](https://pypi.org/project/egms-client/) | `~=0.7.0` | Apache-2.0 |
| [`firms-client`](https://pypi.org/project/firms-client/) | `~=0.5.0` | Apache-2.0 |
| [`ispra-idrogeo`](https://pypi.org/project/ispra-idrogeo/) | `~=0.7.0` | Apache-2.0 |
| [`fwi-chain`](https://pypi.org/project/fwi-chain/) | `~=1.0.0` | Apache-2.0 |
| [`effis-client`](https://pypi.org/project/effis-client/) | `~=0.1.2` | Apache-2.0 |
| [`rainfall-thresholds`](https://pypi.org/project/rainfall-thresholds/) | `~=0.1.0` | Apache-2.0 |
| [`imageserver-export`](https://pypi.org/project/imageserver-export/) | `~=0.2.0` | Apache-2.0 |
| [`dpc-radar`](https://pypi.org/project/dpc-radar/) | `~=0.2.1` | Apache-2.0 |
| [`glofas-ewds`](https://pypi.org/project/glofas-ewds/) | `~=0.1.0` | Apache-2.0 |
| [`mcp-geo-server`](https://github.com/agent-engineering-studio/mcp-geo-server) | Docker image, pinned commit | MIT |

### copernicus-ems

[![PyPI](https://img.shields.io/pypi/v/copernicus-ems)](https://pypi.org/project/copernicus-ems/) ·
[GitHub](https://github.com/agent-engineering-studio/copernicus-ems) · Apache-2.0

**What it does.** Reads [Copernicus EMS Rapid Mapping](https://rapidmapping.emergency.copernicus.eu/),
the service that maps disasters from satellite images within hours. It lists
the activations (e.g. `EMSR664`, Emilia-Romagna, May 2023), their products,
and downloads the **observed event layers** (where the water actually was)
plus the **observation masks** (where the satellite actually looked) as
GeoJSON. No account, no key; one dependency, `httpx`.

**How Limen uses it.** It builds the **flood truth set**: 14 Italian
activations, 15,865 flooded polygons, 3,593 cells in 9 regions. The mask
matters: inside it, *no polygon* means *observed dry*; outside, an alert is
*unverifiable*, not false. Command: `make flood-events`
(`limen ingest-events --hazard flood`), then `limen backtest-flood`. Code:
[`integrations/copernicus_ems/`](./src/limen/integrations/copernicus_ems/).

### egms-client

[![PyPI](https://img.shields.io/pypi/v/egms-client)](https://pypi.org/project/egms-client/) ·
[GitHub](https://github.com/agent-engineering-studio/egms-client) ·
[Docs](https://agentengineering.it/egms-client/) · Apache-2.0

**What it does.** Downloads the archive of [EGMS](https://egms.land.copernicus.eu/),
the European Ground Motion Service: how many **millimetres per year** the
ground moves, measured by the Sentinel-1 radar satellites. It handles the
CLMS service-key login, search, download and caching of the L2A, L2B and
Ortho L3 products, mosaics and GeoParquet time series.

**How Limen uses it.** `limen sync-egms` (run by `make init` when the key is
set) downloads the Ortho L3 tiles for Italy, vertical and east-west at 100 m:
~25 minutes and 164 tiles (~420 MB) the first time, nothing afterwards. Limen
uses the library's search and parsing and fetches the tiles itself
(`integrations/egms/clms.py`), then computes per cell the 90th
percentile of the velocity and the number of valid pixels
(`cell_insar_features`). A nightly step checks for a new release. Needs
`EGMS__SERVICE_KEY`; today it feeds the ML features, not the map. Code:
[`integrations/egms/`](./src/limen/integrations/egms/).

### firms-client

[![PyPI](https://img.shields.io/pypi/v/firms-client)](https://pypi.org/project/firms-client/) ·
[GitHub](https://github.com/agent-engineering-studio/firms-client) · Apache-2.0

**What it does.** Reads [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/):
every active fire seen from space since 2000. It downloads the **open
per-country yearly archives** (no key), queries the **near-real-time area
API** (with a free `MAP_KEY`), and classifies detections, so that a
**vegetation fire is told apart from a steelworks or a volcano**.

**How Limen uses it.** Two ways:
- **History** (`make fire-history`): 391,987 Italian detections →
  224,156 cell-day fire events and a `fire_density` per cell, used by the
  wildfire ML features and to weigh how hard a past fire hit a slope.
  Without the type filter, the "most burnt" place in Italy was the ILVA
  steelworks in Taranto.
- **Live trigger** (`FIRMS__MAP_KEY`): every 45 min, new hotspots in a
  region start a scoring run at once, and the post-fire landslide term
  switches on within hours instead of waiting for the burnt-area map.

Code: [`integrations/firms/`](./src/limen/integrations/firms/).

### ispra-idrogeo

[![PyPI](https://img.shields.io/pypi/v/ispra-idrogeo)](https://pypi.org/project/ispra-idrogeo/) ·
[GitHub](https://github.com/agent-engineering-studio/ispra-idrogeo) · Apache-2.0

**What it does.** Downloads from [IdroGEO](https://idrogeo.isprambiente.it/),
the platform where ISPRA publishes what Italy knows about landslides and
floods: the **IFFI landslide inventory** (721,365 landslides), the national
**PAI hazard mosaics**, dated events, and the REST API with risk figures for
any region, province or municipality. Files are cached and refreshed with
conditional requests, so a nightly update costs a few hundred bytes when
nothing changed.

Since 0.5 it is also:

| | New | In plain words |
|---|---|---|
| 🤖 | **`idrogeo-mcp`, an MCP server** | `pip install "ispra-idrogeo[mcp]"`, add it to Claude Desktop or any agent, and ask *"how many people live in high landslide hazard areas in Sarno, and is anyone monitoring the landslides there?"*. Twelve tools since 0.6: `find_area`, `area_risk`, `area_landslides`, `landslide`, `search_landslides`, `search_events`, `monitoring_sites`, `webcams`, `hazard_at` (the hazard class at a point), `landslides_near` (the landslides around a point), `code_list`, `download_dataset`. All read-only except the download; answers stop at `limit` rows, so an agent never receives 700,000 landslides at once. |
| ⌨️ | **The `idrogeo` command** | `idrogeo fetch frane_piff --area molise`, `idrogeo summary pir comuni 72006`, `idrogeo landslides --since …`: downloads print the folder, everything else prints JSON Lines, ready for `jq` or a database loader. |
| 🗺️ | **GeoDataFrames and GeoParquet** | The `[geo]` extra turns API rows and downloaded layers into GeoPandas tables. |
| 🔎 | **Typed search filters** | Landslides by type of movement and activity, events by area and date, monitoring sites by status, without writing PostgREST syntax. |
| 🏷️ | **Codes decoded** | The API's 73 code lists, in four languages: `strumentazione = [15, 22, 25]` becomes inclinometer, topographic monitoring, SAR interferometry. |
| 🔁 | **Only what changed** | `modified_since` for incremental updates of landslides, events and monitoring sites. |
| 📡 | **Monitoring sites and webcams** | Who is watching a landslide, with which instruments. |

```json
{ "mcpServers": { "idrogeo": { "command": "idrogeo-mcp" } } }
```

In this repository `.mcp.json` already wires it for Claude Code, through
`uvx` in an environment of its own: the MCP server needs `mcp>=2.0`, while
Limen's own MCP server runs on `fastmcp` and `mcp` 1.x, so the two are never
installed together.

**How Limen uses it.** `limen geodati-sync`, step 3 of the static data at
`make init`, downloads with it the IFFI inventory of every region (plus
Bolzano and Trento) and the national PAI landslide and flood mosaics into
`GEOSERVER_SHAPEFILE_DIR`, to be loaded into the mcp-geo-server PostGIS. Limen
uses its client directly, because the files (up to 1.2 GB) must be streamed
to disk: with `retries=0`, inside Limen's own retry policy. ISPRA regenerates the IFFI files every night, so a file is asked
for again only after `GEODATI__RIVALIDA_DOPO_GIORNI` (30 days). Code:
[`integrations/idrogeo/`](./src/limen/integrations/idrogeo/).

### imageserver-export

[![PyPI](https://img.shields.io/pypi/v/imageserver-export)](https://pypi.org/project/imageserver-export/) ·
[GitHub](https://github.com/agent-engineering-studio/imageserver-export) ·
[Docs](https://agentengineering.it/imageserver-export/) · Apache-2.0

<p align="center">
  <img src="https://raw.githubusercontent.com/agent-engineering-studio/imageserver-export/main/docs/images/map-milan.png" alt="Map of Milan and its belt: the share of sealed soil in each 100 m pixel, exported with imageserver-export" width="70%">
</p>

**What it does.** Turns an area of any **ArcGIS ImageServer** into one clean
GeoTIFF. Its first use is the open server of the European Environment
Agency, which publishes the **Copernicus Land Monitoring Service** maps of
Europe at 10 m: sealed soil, tree cover, grassland, water and wetlands, with
no account. The library snaps the area to whole pixels so the tiles line up,
keeps the "no data" values intact (nearest neighbour, never bilinear),
catches the errors the server sends with "200 OK", and writes the file only
when every tile is in.

**How Limen uses it.** `limen imperviousness-fetch` (and `make fetch-static`)
downloads with it the **sealed-soil** raster for every seeded AOI, at 100 m
in LAEA Europe; the per-cell factor that amplifies the rain-driven flood
trigger is computed from it. Every request goes through Limen's
`fetch_with_retry` (the library's `send` hook). An interrupted download
resumes from the tiles already in, and the file carries its provenance
(service URL, interpolation, valid range) as GeoTIFF tags. Code:
[`integrations/imperviousness/`](./src/limen/integrations/imperviousness/).

**For AI agents.** `imageserver-mcp` (`pip install "imageserver-export[mcp]"`)
lets an agent read any ImageServer: `describe_layer`, `sample_point` (the
value at a place, with its label), `area_summary` (mean, valid share and
class counts of a box), `export_area`. Every number comes from the library,
not from the model, the same rule as Limen's summaries. `.mcp.json` wires it
for Claude Code through `uvx`, next to `idrogeo-mcp`, for the same reason
(`mcp>=2.0` in its own environment). Ask *"how much of the ground is sealed
around Sarno, and what is the tree cover upslope?"*.

### mcp-geo-server

[GitHub](https://github.com/agent-engineering-studio/mcp-geo-server) · MIT

**What it does.** A ready-to-run GIS stack in Docker: **PostGIS + GeoServer**
plus a one-shot bootstrap that loads shapefiles from a folder and publishes
them as OGC WMS/WFS layers with thematic styles, and an **MCP server** where
an AI agent drives GeoServer in natural language ("how many landslides in the
Marche?"), with a chat-and-map web UI.

**How Limen uses it.** It is **optional** (`LIMEN_GEOSERVER=1`, #426): it
publishes the ISPRA layers as WMS overlays for the map (`/geoserver/ispra/wms`)
and gives AI agents a GeoServer to talk to. The numbers do not depend on it:
`limen carica-vettori` loads the IFFI inventory, the PAI and hydraulic mosaics
and the ISTAT borders into Limen's own database (schema `sorgenti`), with the
same table names GeoServer used, and `geoserver-sync`, `bootstrap-static` and
`seed-comuni` read them from there. `make static-data` does both; by hand:

```bash
uv run limen geodati-sync     # download the base data into $LIMEN_DATA_ROOT/geoserver
uv run limen carica-vettori   # load the vectors into Limen's database (skips unchanged ones)
make geoserver-sync           # copy IFFI, PAI and hydraulic hazard into the operational tables
make geoserver-up             # optional: GeoServer :8081, web UI :8000, MCP :9000
make geoserver-init           # optional: publish the shapefiles as WMS layers
```

Nothing in the hourly scoring path waits on GeoServer. Compose file:
[`infra/docker/docker-compose.geoserver.yml`](./infra/docker/docker-compose.geoserver.yml).

### Also extracted from Limen

| Library | What it does | Used in Limen for |
|---|---|---|
| [`fwi-chain`](https://pypi.org/project/fwi-chain/) | The Canadian Fire Weather Index (Van Wagner 1987), pure and verified against the published reference day to 1e-9 | the wildfire engine, one chain per weather node |
| [`effis-client`](https://pypi.org/project/effis-client/) | EFFIS burnt-area perimeters and the official FWI maps (a MapServer with many surprises) | wildfire truth set; `limen fwi-confronto` |
| [`rainfall-thresholds`](https://pypi.org/project/rainfall-thresholds/) | Rainfall events and intensity–duration thresholds (Caine) | the landslide rain term |
| [`glofas-ewds`](https://pypi.org/project/glofas-ewds/) ([site](https://agentengineering.it/glofas-ewds/)) | GloFAS 4 discharge and the Copernicus FWI from the EWDS, read on the cell Open-Meteo serves (the declared one, one step east): requests, monthly re-runnable downloads, readers per node, a river's own reference | `limen glofas-ewds` (node references), the daily GloFAS forecast run, `limen fwi-confronto` |

---

## Architecture

```mermaid
flowchart LR
    SRC["Open data sources<br/>(see above)"] -->|httpx + retries| WK
    GS["mcp-geo-server<br/>GeoServer + PostGIS<br/>ISPRA layers"] -->|bootstrap| DB
    subgraph WK["limen worker · APScheduler"]
        H["hourly sweep<br/>score · persist · alert"]
        FC["72 h forecast<br/>4× a day"]
        NT["nightly<br/>ML shadow · drift · backup"]
        BR["regional<br/>summaries"]
    end
    WK --> DB[("PostgreSQL 16<br/>+ PostGIS")]
    BR <--> LLM["LiteLLM gateway<br/>llama.cpp · Claude"]
    WK --> N["Telegram · e-mail<br/>MQTT · webhook"]
    DB --> API["FastAPI<br/>REST + A2A"]
    DB --> T["pg_tileserv<br/>vector tiles"]
    DB --> MCP["MCP limen-ops<br/>for AI agents"]
    API --> SPA["React + MapLibre<br/>public map"]
    T --> SPA
    GS -->|WMS overlays| SPA
```

**In short:** a **worker** process fetches data and computes scores on a
schedule; everything lands in **PostgreSQL + PostGIS**; the **API**, the
**tile server** and the **MCP server** read from it; the **map** is a static
React app. The AI sits on the side, writing summaries.

| Layer | Technology | Why |
|---|---|---|
| Language | Python 3.12, [`uv`](https://github.com/astral-sh/uv), `mypy --strict` | typed end to end, one lockfile |
| Database | PostgreSQL 16 + PostGIS, `asyncpg`, plain-SQL migrations, **no ORM** | same code on Docker, Neon or any Postgres |
| Scheduling | APScheduler in `limen worker` (`pg_cron` optional) | works where `pg_cron` doesn't (Neon) |
| API | FastAPI: `/api/...`, `/docs`, `/redoc`, `/health`, A2A at `/a2a` | OpenAPI for free |
| Map | Vite + React + Mantine + MapLibre GL, pg_tileserv vector tiles | no Node server, fast tiles |
| AI | LiteLLM gateway → llama.cpp (local) or Claude; MCP + A2A for agents | local first, cloud opt-in, capped spend |
| Storage | `filesystem` or any S3-compatible store (MinIO, R2, B2) | no cloud SDK lock-in |
| Deploy | Docker Compose on one self-hosted server | no AWS, no Azure, no GCP |

<details>
<summary><b>Every component in detail</b></summary>

| Component | What it does | Cadence | Implementation |
|---|---|---|---|
| **Open-Meteo** | hourly precipitation, soil moisture 0–7 / 7–28 cm, snow (forecast); accumulated precipitation (archive). Served by **our own instance** (compose profile `meteo`): the public API's 10,000 calls/day were exhausted by the sweep and left flood and wildfire at zero across Italy (#142) | live, 30 min cache | `integrations/openmeteo/` + `CachedOpenMeteoClient` |
| **ISPRA (GeoServer PostGIS)** | IFFI inventory, PAI landslide mosaic; the hydraulic mosaic feeds the flood susceptibility and the landslide `H` component | at init | `limen geodati-sync` (IdroGEO download) + `integrations/geoserver_source/` |
| **Copernicus EWDS — GloFAS** | per-node river discharge forecast (`cems-glofas-forecast`, control run) and each node's **ordinary high flow** (`glofas_riferimento`), the denominator of the fluvial ratio | forecast 4×/day, references nightly | `integrations/copernicus/` |
| **Copernicus Land — EGMS** | Ortho L3 ground motion: per-cell p90 velocity and valid pixels | yearly sync + nightly release check | `integrations/egms/` + `limen sync-egms` |
| **DPC radar** | SRI (1 km / 5 min) as a nowcast trigger; «Merging» accumulation at each cell for floods (#199) | every `NOWCAST__INTERVAL_MINUTES` / per sweep | `integrations/dpc/` |
| **INGV** | FDSN events (mag ≥ 3.5, last 7 days); ShakeMap grid | event-driven | `integrations/ingv/` |
| **EFFIS** | burnt-area perimeters (public **MapServer**, no credentials) | weekly | `integrations/effis/` |
| **NASA FIRMS** | VIIRS/MODIS hotspots, NRT trigger + per-country archive | every `FIRMS__INTERVAL_MINUTES` | `integrations/firms/` |
| **Copernicus EMS** | observed flooded areas + observation masks | one-shot | `integrations/copernicus_ems/` |
| **Static bootstrap** | per-cell `iffi_density_500`, `distance_to_iffi_m`, `pai_class_norm`, `slope_deg`, land cover, geology, WUI; skips unchanged sources (#101) | one-shot | `integrations/static_bootstrap/` |
| **Scoring engine (V1)** | Caine I/D threshold (re-fitted on ITALICA), sigmoid antecedent rain, post-fire window modulated by burn severity, seismic decay, weighted aggregator + 5 classes | pure (no I/O) | `core/scoring/` |
| **Hazard registry** | engines registered per *(hazard, implementation)*; one YAML per hazard | cross-cutting | `core/scoring/registry.py`, `config/hazards/` |
| **ML challenger** | LightGBM on spatial-block CV; runs in shadow every night; promotion only by hand | nightly | `ml/` + `limen train` |
| **Predictive forecast** | scoring at `now+H` with forecast rain; "FORECAST" alerts with their own dedup | 4×/day | `agents/workflows/forecast.py` |
| **Regional summaries** | Italian and English narratives per region and hazard, stored in `spiegazioni_regione`; a fallback text is marked as such | asynchronous | `api/jobs/briefing_enrichment.py` |
| **MCP `limen-ops`** | `tool_risk_summary`, `tool_top_risk_cells`, `tool_cell_breakdown`, `tool_recent_alerts`, `tool_national_report`, `tool_comune_risk`, `tool_top_comuni` + admin tools behind `MCP_ADMIN_TOKEN` | HTTP `127.0.0.1:8766/mcp` | `mcp/` + `limen mcp-serve` |
| **A2A** | JSON-RPC 2.0 Agent Card at `/.well-known/agent-card.json`, `/a2a` with `message/send`, `message/stream`, tasks | read-only | `a2a/` |
| **Vector tiles** | `mv_latest_risk`, `risk_at(z,x,y,hours_ago,hazard)`, `forecast_at(z,x,y,horizon,hazard)` via pg_tileserv | per cycle | migrations `007`, `060` |
| **Per-comune rollup** | `mv_comune_risk`: worst cell, class profile, exposure ranking; REST `/api/comuni` | per cycle | migration `026_comuni.sql` |
| **Reports** | daily national report on the alert channels; static HTML report of the riskiest zones with an immutable archive; regions PDF | daily / hourly | `api/jobs/`, `report/`, `limen report build` |
| **Notifications** | `NotificationChannel` protocol: Telegram, MQTT, e-mail, webhook; parallel dispatcher, per-channel isolation, dedup | per tick | `notifications/` |

Database highlights: `aoi`, `grid_cells`, `cell_static_factors`,
`risk_assessments` and `model_runs` (partitioned by UTC day), `latest_risk`,
`training_samples`, `fwi_state`, `glofas_riferimento`, `glofas_previsione`,
`cell_insar_features`, `spiegazioni_regione`, `alert_dispatches`,
`fire_perimeters`, `landslide_events`, `schema_migrations`. Geometries in
EPSG:4326; distances and areas in EPSG:3035. More in
[`docs/architecture.md`](./docs/architecture.md) and
[`docs/data-model.md`](./docs/data-model.md).

</details>

<details>
<summary><b>Why these choices</b></summary>

| Decision | Rationale |
|-----------|-------------|
| **Engine-agnostic PostgreSQL 16 + PostGIS** (no BaaS, no ORM) | Same SQL and code on local Docker, Neon or self-hosted. Only `DB__CONNECTION_STRING` changes. |
| **`asyncpg` + a custom PostGIS codec** | Geometries travel as Shapely objects: no WKB boilerplate. |
| **Optional `pg_cron`** | Neon does not support it; APScheduler runs the same jobs. |
| **Object storage behind a Protocol** | Raster bytes never go into the DB; any S3-compatible endpoint, never a cloud SDK. |
| **Plain SQL migrations** | A runner with checksums; identical behaviour on every Postgres. |
| **GeoServer as a generic data source** | mcp-geo-server publishes the ISPRA data; ISPRA semantics live only in Limen's loader. |
| **Copernicus data at the source** | GloFAS from the EWDS and EGMS from the CLMS archive: Open-Meteo cannot host GloFAS, and its cell is one step east of the one it declares — on the Toce, a factor of ten. |
| **One worker, three cadences** | Hourly scoring without AI fits in the tick; summaries are asynchronous; ML and maintenance run at night. |

</details>

---

## Does it work? What we measured

We test every formula against **real past events** and publish the numbers,
including the uncomfortable ones.

<p align="center">
  <img src="docs/images/wildfire-backtest.svg" alt="Wildfire backtest in Basilicata: in 2025, 79% of days with a real fire were in Limen's high class, against a base rate of 43%; in 2024, 100% against 28%." width="100%">
</p>

**Why two bars.** A system that says "danger" every summer day catches every
fire and is useless. So every check reports the **hit rate** (how often a
real event had been flagged) **next to the base rate** (how often the system
flags anyway). The gap between them is the skill.

| What | Result | Against |
|---|---|---|
| Wildfire, Basilicata 2025 (EFFIS perimeters) | **79 %** hit rate | 43 % base rate |
| Wildfire, Basilicata 2024 | **100 %** hit rate | 28 % base rate |
| Landslide ML challenger (37k samples, spatial-block CV) | **AUC-PR 0.60** | 0.28 for the deterministic engine |
| Wildfire ML challenger (one season, 30,066 samples) | **AUC-PR 0.352** | 0.237 for FWI alone |
| Landslide rain threshold re-fitted on e-ITALICA | ~95 % of real landslides above threshold | 64 % with the historical threshold |
| Real landslides reaching ≥ Moderate (rain-gauge rainfall) | ~63–77 % | — |

**Where we honestly stand** (#122). With reanalysis rainfall, the **"high"**
landslide class still catches few landslides: Liguria, November 2019, 11 % of
131 landslides with 0.17 % of cell-hours on alert; the Marche, May 2014, none
of 172. The score ranks cells well within a region, but the rainfall signal as
we read it today is the limit, and it is the next piece of work. The ML
models stay **challengers** in shadow mode: the deterministic engine remains
the authoritative one until a model beats it on spatial cross-validation and
the backtest, and promotion is a manual decision.

Run the checks yourself: `limen backtest`, `limen backtest-flood`,
`limen backtest-wildfire`, `limen verifiche-report`.

---

## Installing on a server

Limen needs **only Docker** on the host, plus the repository and a `.env`.
The `limen` commands run inside the worker container; the periodic jobs live
in the worker, not in the host's crontab.

```sh
git clone https://github.com/agent-engineering-studio/limen.git && cd limen
cp .env.example .env                   # at least LIMEN_DATA_ROOT (absolute)
./scripts/nuovo_host.sh --controlla    # check prerequisites only, changes nothing
./scripts/nuovo_host.sh --ripristina   # restore from the nightly backup (needs BACKUP__*)
./scripts/nuovo_host.sh --da-zero      # a fresh stack: seed, events, calibration, FWI
```

`--controlla` checks Docker and Compose, free space under `LIMEN_DATA_ROOT`
(`NUOVO_HOST_DISCO_GB`, 50) and the **fsync latency** of the Docker disk
(`NUOVO_HOST_FSYNC_MS_MAX`, 20 ms): on a disk at ~1 s per fsync, `initdb`
times out. The other two modes are re-runnable and end with
`limen data-status` and `limen jobs`.

**What fills in by itself, and when.** The map: the first hourly sweep, within
the hour. The per-cell forecast: 02, 08, 14 and 20:20 UTC. The FWI chain
needs a month of spin-up after `fwi-backfill`; a restore brings it back
settled. The GloFAS references: a share of nodes every night, weeks for all.

### Pitfalls met on a real install (macOS host)

What went wrong bringing up a fresh stack on an Intel Mac with Docker
Desktop, and the fix for each:

| Symptom | Cause | Fix |
|---|---|---|
| `uv sync --all-groups` fails: *torch … doesn't have a wheel for the current platform* (then the same for `onnxruntime`) | PyTorch stopped publishing macOS x86_64 wheels after 2.2, onnxruntime soon after; the `dl` and `ml` groups need newer ones | on an Intel Mac `uv sync --all-groups --no-group dl --no-group ml`. Only the V2 ML shadow stack needs them; the V1 engine, API and worker do not. Apple Silicon and Linux install everything |
| `make` stops at once: *unterminated call to function 'shell'* | macOS ships GNU make 3.81 (2006); the Makefile needs ≥ 4.3 | `brew install make`, then `export PATH="/usr/local/opt/make/libexec/gnubin:$PATH"` (`/opt/homebrew/...` on Apple Silicon) in `~/.zshrc`. `nuovo_host.sh` calls `make`, so run it with that `PATH` |
| `--da-zero` dies mid-seed with `Error 255`, Docker socket gone | Docker Desktop auto-updated and restarted itself | Docker Desktop settings: turn off *Automatically download updates* and *Resource Saver*, turn on *Start Docker Desktop when you sign in*; on the host `sudo pmset -a sleep 0 disksleep 0`. The script is re-runnable: launch it again |
| `geoserver-init` "stops immediately" and the map has no IFFI/PAI | it is a one-shot job (exits 0); `make static-data` used to skip the download when `GEOSERVER_SOURCE__DB_DSN` was unset | fixed by #426: the download always runs and `limen carica-vettori` loads the vectors into Limen's database, no variable needed. GeoServer is opt-in (`LIMEN_GEOSERVER=1`) |
| the Mac (i9, 16 GB) swaps, the API takes minutes to start, healthchecks time out | the full stack is 17 containers; GeoServer alone is 1.4 GB of Java at 300 % CPU even when idle | since #426 `make up` starts the essential profile (7 containers); `LIMEN_GEOSERVER=1` and `LIMEN_AGENTI=1` add the rest |
| `data-status` reports the sealed-soil layer missing for flood | the raster is not part of `static-data` | `make imperviousness-data`, set `LIMEN_IMPERVIOUSNESS_RASTER` to the printed path, `make bootstrap-static` (only the new step runs) |

With `LIMEN_IMAGE_PREFIX` set, the published SPA needs the reverse proxy
even on a single machine: `LIMEN_DOMINIO=localhost` plus
`LIMEN_PROXY_BIND=127.0.0.1` gives Caddy on `https://localhost` with an
internal certificate.

### Updating production: `make deploy`

Production runs from a detached worktree next to the development checkout
(`../limen-deploy`, `DEPLOY_DIR`), with the same compose project, `.env` and
volumes as `make up`:

```sh
make deploy                       # production to origin/main
make deploy DEPLOY_REF=3eadcda    # a given commit, also to go back
```

It refuses to start if that commit's tests are not green on CI or the
worktree has local changes; otherwise it rebuilds `api`, `worker`, `mcp`
(and the SPA when `frontend/` changed), waits for `/ready` and records the
commit in `refs/deploy/ultimo`. Migrations are applied by the API at
start-up. Never run `make up` in the development checkout on the production
host: it shares the compose project and would deploy whatever is checked out.

<details>
<summary><b>Images, static data, LLM gateway, reverse proxy</b></summary>

### Images: built here or pulled from GHCR

By default the compose files **build** the images on the host. Every push to
`main` and every `vX.Y.Z` tag also publishes them on GHCR, tagged
`sha-<commit>`, `main`/`latest` and the version:

```sh
# in .env
LIMEN_IMAGE_PREFIX=ghcr.io/agent-engineering-studio/limen-
LIMEN_IMAGE_TAG=sha-7a8dd95       # or 0.7.0; never latest on a server
```

With the prefix set, `make up` pulls instead of building, and a rollback is
the previous tag. The published SPA calls everything **on its own origin**,
so the reverse proxy routes `/api/` to the API (`:8080`), `/tiles/` to
pg_tileserv (`:7800`) and `/geoserver/ispra/wms` to GeoServer (`:8081`, WMS
only). Images are `linux/amd64`. Third-party images are pinned (pg_tileserv
`20250131`, Open-Meteo `1.6.0`, mcp-geo-server at its commit).

### Static data

- **Static snapshot** (#305): `limen static-snapshot export` dumps the
  computed per-cell factors (instead of the ~47 GB of rasters they come
  from) to the backup store; `limen static-snapshot import` loads them on a
  new instance after `migrate` and `seed`. Then `limen calibrate`.
- **`make fetch-static`** downloads what needs no account: the CLMS
  sealed-soil raster and the OSM roads and railways, with a manifest of
  sizes and sha256. DTM, CORINE, geology and the ISPRA layers are downloaded
  by the static-data step of `make init` (see the Quick start).
- **`make static-data`** runs the same commands on the host when `uv` is
  there, otherwise in a throwaway worker container.

### LLM gateway without a GPU

`make inference-up-cpu` starts LiteLLM and a CPU embedding service with the
same model names as the GPU stack. Without a cloud key, summaries fall back to
a deterministic text: **the map and the alerts never depend on an LLM.** See
[`docs/inference.md`](./docs/inference.md).

### Reverse proxy and certificates

Set `LIMEN_DOMINIO` and `make up` adds Caddy on 80 and 443 with Let's Encrypt
certificates and the same routes as
[`infra/nginx/`](./infra/nginx/). Without it, use your own proxy.

</details>

### Published ports: Docker bypasses ufw

Docker writes its own iptables chains, consulted *before* ufw's: the host's
`default deny incoming` does **not** protect a published container port. So
every `ports:` entry binds to a `LIMEN_*_BIND` variable defaulting to
`127.0.0.1` (`LIMEN_PG_BIND`, `LIMEN_API_BIND`, `LIMEN_MQTT_BIND`,
`LIMEN_TILESERV_BIND`, `LIMEN_FRONTEND_BIND`, `LIMEN_MCP_BIND`,
`LIMEN_GEOSERVER_*_BIND`, `LIMEN_IDROGEO_MCP_BIND`). Public exposure goes
through a reverse proxy on 443, never by binding to `0.0.0.0`.

---

## Backup and restore

Limen backs up its **state** every night, off the server. The database is
about 31 GB, but almost all of it can be rebuilt; what cannot fits in ~2 GB
(verified events, training samples, sensor data, narratives, alerts, the FWI
chain, the GloFAS references). Measured on production data: a **202 MB** dump
in **41 s**, restored and verified in **62 s**.

```sh
make backup                      # a backup now, from the worker
make backup-elenco               # list complete backups on the bucket
make restore CONFERMA=1          # restore the latest (API and worker stopped)
make restore CONFERMA=1 CHIAVE=backup/2026-10-24T02-05-00Z/
uv run limen sensore ripristina-ca --dove "$LIMEN_SENSORI_DIR"   # sensors CA, on the host
```

<details>
<summary><b>What is saved, what restore refuses, restoring by hand</b></summary>

The `backup` step of the nightly job writes `backup/<UTC time>/` to a
dedicated S3-compatible bucket (`BACKUP__*`, separate from `OBJECT_STORE__*`):

| File | Content |
|---|---|
| `limen.dump` | `pg_dump --format=custom`: every table's schema; data of all except `BACKUP__SOLO_SCHEMA` (hot, derived or reloadable) |
| `mlflow.dump` | the MLflow registry, when it is a PostgreSQL database on the same server |
| `ruoli.sql` | roles without passwords (restricted roles get theirs from `DB__*_PASSWORD`) |
| `mlruns.tar.gz` | the folders in `BACKUP__CARTELLE` (MLflow artifacts) |
| `manifest.json` | written last: sizes, sha256 and **row count of every saved table**; a backup without it was interrupted |

Backups older than `BACKUP__RETENTION_GIORNI` (30) are deleted, but the last
`BACKUP__TIENI_ALMENO` (3) always stay, and a backup with less than half the
rows of the previous one suspends deletion. A last good backup older than
`BACKUP__ETA_MASSIMA_ORE` (36) logs `integration.degraded label=backup.stale`.

The **sensors CA** is saved encrypted (scrypt + AES-256-GCM, passphrase in
`BACKUP__PASSPHRASE_CA`). **Keep a copy of the passphrase off the server**:
without it the CA backup cannot be opened.

**What restore refuses:** a restore that does not find every row the
manifest promises; a database with other clients connected; a database at a
different migration than the backup (`--forza` overrides the last two).

**By hand, in order:** (1) Docker, repo and `.env` with `BACKUP__*`;
(2) `make db-up`; (3) `make restore CONFERMA=1`; (4) if you run the sensors
network, `limen sensore ripristina-ca`, `make sensori-ca-init`,
`make sensori-up`; (5) `make up`; (6) wait for the hourly sweep and reload
ISPRA layers with `make static-data`; (7) check with `limen data-status`,
`limen jobs` and the map. `./scripts/nuovo_host.sh --ripristina` does steps
2–5.

Not included: the local radar archive (`RADAR_ARCHIVE__CARTELLA`, ~51 GB;
add it to `BACKUP__CARTELLE` if older months matter).

</details>

---

<details>
<summary><b>Python dependency groups</b></summary>

Everything goes through `uv` (`uv sync --all-groups` for the full set). The
runtime dependencies are in `pyproject.toml`; the optional ones are grouped
by what needs them:

| Group | For | Main packages |
|---|---|---|
| _(runtime)_ | API, worker, CLI | asyncpg, shapely, geopandas, rasterio, pydantic, httpx + tenacity, APScheduler, FastAPI, structlog, OpenTelemetry, the extracted libraries |
| `ml` | V2 ML engine, training, drift | LightGBM, scikit-learn, MLflow, Optuna, SHAP, ONNX Runtime |
| `dl` | deep-learning experiments | PyTorch, ONNX |
| `agents` | the Message Batch faithfulness reviewer | anthropic |
| `mcp` | MCP server | fastmcp |
| `report` | PDF/HTML reports | Jinja2, ReportLab |
| `copernicus` | EWDS (GloFAS, FWI comparison) | cdsapi, netCDF4 |
| `radar` | DPC radar archive | numcodecs |
| `storage` | S3-compatible object store | boto3 (imported only by the object-store factory) |
| `dev` | tests and gates | pytest, ruff, mypy, testcontainers, respx |

</details>

## Testing and quality gates

```bash
make check                 # the gate: lint + typecheck + tests (coverage ≥ 80 %) + doc links
make test-unit             # fast, no Docker
make test                  # unit + integration (testcontainers)
make test-slow             # national-seed tests (deselected by default)
make lint && make format   # ruff
make typecheck             # mypy --strict on src/
( cd frontend && npm test && npm run lint )
```

On Apple Silicon set `LIMEN_TEST_POSTGIS_IMAGE=imresamu/postgis-arm64:16-3.5`;
`LIMEN_TEST_DATABASE_URL` points the tests at an existing PostGIS.

---

## Status and roadmap

**Done:** three hazards in production on all 20 regions; a 72-hour per-cell
forecast four times a day; Italian and English; Copernicus data at the
source (GloFAS from the EWDS, EGMS from the CLMS archive); a «Regions to
watch» page with PDF reports; DPC radar nowcast and NASA FIRMS fire
triggers; an ML challenger in nightly shadow mode with public diagnostics;
MCP and A2A interfaces for AI agents; webhook alerts; an open sensors
network; nightly off-site backups.

**Next:**
- **The rainfall signal for landslides** (#122): hourly intensity vs.
  accumulation, the 48-hour window, Caine thresholds per macro-region —
  always tuned on one group of regions and checked on the others.
- **Shadow verdict** of the ML challenger (`limen shadow-report`); promotion
  stays manual.
- **Reliability plot** for the ML diagnostics, once there are enough real
  events (#30).

See [`ROADMAP.md`](./ROADMAP.md) and [`CHANGELOG.md`](./CHANGELOG.md).

<details>
<summary><b>Design decisions worth knowing</b></summary>

- **No user authentication, by design** (epic #69). Limen is a public map:
  every API feeding it was always public, so a login protected the page, not
  the data. The only privileged action, launching a sweep, lives on the CLI
  (`limen monitor-once`) and on MCP behind `MCP_ADMIN_TOKEN`.
- **The deterministic engine stays the champion.** It is never removed or
  weakened; an ML model must beat it on spatial-block CV and on the backtest,
  and an operator promotes it by hand.
- **Agents.** `limen mcp-serve` exposes risk, alerts and reports as MCP tools
  (OpenClaw, Claude Desktop):
  `openclaw mcp set limen-ops '{"url":"http://127.0.0.1:8766/mcp","transport":"streamable-http"}'`.
  Alerts can also be pushed to an agent gateway via webhook.

</details>

---

## Licences and attribution

### The code

| Component | Licence |
|---|---|
| **Limen** (this repository) | [EUPL-1.2](./LICENSE) — copyleft that also covers network use: whoever offers Limen as a service must publish their changes. Versions up to `v0.6.0-impl-complete` remain Apache-2.0. A commercial licence is available for uses incompatible with copyleft. |
| copernicus-ems, egms-client, firms-client, ispra-idrogeo, fwi-chain, effis-client, rainfall-thresholds, glofas-ewds | Apache-2.0 |
| mcp-geo-server | MIT |

External contributions require the CLA in
[`CONTRIBUTING.md`](./CONTRIBUTING.md#contributor-license-agreement).

### The data

Attribution is **mandatory** when you publish the map, the summaries or
anything derived from them:

* **ISPRA IdroGEO** (IFFI) — © ISPRA, CC-BY 4.0.
  <https://idrogeo.isprambiente.it>
* **ISPRA hazard mosaics** — CC BY SA 4.0, as stated by the licence PDF in each
  download: data derived from them must be distributed under the same licence.
  Citations: «ISPRA - Mosaicatura nazionale delle aree a pericolosità da frana
  PAI (v. 4.0 – 2020-2021), https://idrogeo.isprambiente.it» and «ISPRA -
  Mosaicatura delle aree a pericolosità idraulica (v. 5.0 – 2020),
  https://idrogeo.isprambiente.it». They are technical and scientific works:
  the maps with legal value are those of the basin district authorities.
* **e-ITALICA** (CNR-IRPI) — CC-BY 4.0, DOI
  [10.5281/zenodo.14204473](https://doi.org/10.5281/zenodo.14204473).
* **Open-Meteo** (ECMWF, DWD, Copernicus ERA5 / CERRA) — CC-BY 4.0.
  <https://open-meteo.com>
* **Copernicus EMS — GloFAS** — CEMS-Floods licence: publishers of derived
  data must state **«Contains modified Copernicus Emergency Management
  Service information [year]»** and must not present it as a flood warning.
  Limen does so on the map, the home footer, flood articles and the regions
  PDF (`frontend/src/lib/attribuzioni.ts`, `report/regioni_pdf.py`).
  Real-time EFAS data restricted by art. 12 of Reg. (EU) 1159/2013 must not be
  republished. <https://ewds.climate.copernicus.eu>
* **Copernicus EMS — CEMS Fire** (`cems-fire-historical-v1`) — CC-BY 4.0.
* **Copernicus EMS Rapid Mapping** — © European Union, free with attribution.
  <https://rapidmapping.emergency.copernicus.eu>
* **Copernicus Land — EGMS** and imperviousness — Copernicus Land open licence
  (Reg. EU 2021/696): cite «Generated using European Union's Copernicus Land
  Monitoring Service information» and state the modifications.
  <https://egms.land.copernicus.eu>
* **INGV** (FDSN events, ShakeMap, TINITALY) — CC-BY 4.0. <https://terremoti.ingv.it>
* **EFFIS** (burnt-area perimeters, FWI) — Copernicus EFFIS terms.
* **NASA FIRMS** — free use with acknowledgement: «We acknowledge the use of
  data and imagery from LANCE FIRMS operated by NASA's Earth Science Data and
  Information System (ESDIS) with funding provided by NASA Headquarters.»
  <https://firms.modaps.eosdis.nasa.gov>
* **DPC radar platform** (SRI, «Merging») — CC-BY-SA 4.0.
* **CORINE Land Cover 2018 Italy** (SINAnet/ISPRA) — CC-BY.
* **Geolithological Map of Italy 1:500k** (PCN/MASE) — CC-BY 4.0.
* **ISTAT** (2023 administrative boundaries) — CC-BY.
* **OpenStreetMap** (basemap, roads, railways) — © OpenStreetMap
  contributors, ODbL.

---

## Support Limen

Limen is developed and hosted by [Agent Engineering Studio](https://www.agentengineering.it)
on its own server, with no advertising and no collection of personal data.
Autumn brings the rains, and the rains bring landslides and floods: that is
when an open map of the danger is most useful.

* ⭐ **Star** this repository (and the [libraries](#the-companion-libraries)):
  it helps people working on civil protection, geology and open data find it.
* 🔁 **Share** the [live map](https://limen.agentengineering.it/?lang=en) and
  tell us, with an issue, where the estimated danger does not look right.
* ☕ **Buy us a coffee**: it covers the server, the weather archives and the
  time to tune the engine on real data.

  <a href="https://www.buymeacoffee.com/f9t3zol"><img src="https://img.buymeacoffee.com/button-api/?text=Buy%20me%20a%20coffee&emoji=&slug=f9t3zol&button_colour=FFDD00&font_colour=000000&font_family=Cookie&outline_colour=000000&coffee_colour=ffffff" alt="Buy me a coffee" height="40"></a>
* 🏛️ **Public bodies, municipalities, universities**: for trials on your
  territory, write to us from [agentengineering.it](https://www.agentengineering.it).

## How it was built

Limen has been developed with [Claude Code](https://claude.com/claude-code)
since its first commit, on 3 June 2026: most commits are written together
with Claude, as the `Co-Authored-By` line of each one says. The regional
summaries are written with Claude, Anthropic's model, and change no number.
Limen is an independent project, not affiliated with Anthropic.

## Contributing and governance

* [`CONTRIBUTING.md`](./CONTRIBUTING.md) — dev setup, commit style, gates, CLA.
* [`SECURITY.md`](./SECURITY.md) — private disclosure; threat model in
  [`.oss-scanner/threat_model.md`](./.oss-scanner/threat_model.md).
* [`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md) · [`ROADMAP.md`](./ROADMAP.md) ·
  [`CHANGELOG.md`](./CHANGELOG.md) · [`docs/OSS_IMPACT.md`](./docs/OSS_IMPACT.md)
* Deeper docs: [`docs/architecture.md`](./docs/architecture.md),
  [`docs/scoring-model.md`](./docs/scoring-model.md),
  [`docs/api.md`](./docs/api.md), [`docs/deployment.md`](./docs/deployment.md),
  [`docs/runbook.md`](./docs/runbook.md), [`docs/inference.md`](./docs/inference.md),
  [`docs/openclaw.md`](./docs/openclaw.md).

## Licence

Copyright © 2026 Giuseppe Zileni. Limen is a personal project, developed
outside any employment relationship and with the author's own means: the
rights holder is the author, who is also the party to whom the CLA grants the
licences. Code under [EUPL-1.2](./LICENSE); see
[Licences and attribution](#licences-and-attribution).
