# Integrations: API, MCP & A2A

**Other systems can read Limen in five ways: a public REST API, the map's
vector tiles, two MCP servers for agent gateways, the A2A protocol for
agent-to-agent interoperability, and push notifications to external
channels.** All of them are read-only with respect to the score: no
integration can alter a risk value, and the few actions that write
(launching a monitoring run, rebuilding a report) sit behind an admin token
that switches them off when it is not set.

## Overview: five ways to read Limen

| Surface | For whom | Where | Authentication |
|---|---|---|---|
| REST API | applications, scripts, dashboards | `/api/...` on port 8080 (default) | none |
| Vector tiles | web maps (MapLibre, OpenLayers, QGIS) | pg_tileserv, or the `/api/tiles/...` proxy | none |
| MCP `limen-ops` and `ispra-geo` | agent gateways (OpenClaw, Claude Desktop, …) | `:8766/mcp` and `:8765/mcp` | open reads; writes with `MCP_ADMIN_TOKEN` |
| A2A | third-party agents | `/.well-known/agent-card.json` + `POST /a2a` | none (read-only) |
| Push notifications | Telegram, MQTT, email, webhook | configured on the server | the channel's own |

They all read the same numbers: those the deterministic engine wrote in the
latest hourly run. No surface recomputes a score at request time, so two
clients asking for the same cell at the same moment get the same value.

## REST API

**A public HTTP/JSON API with no login, also documented in OpenAPI format
at `/docs`, `/redoc` and `/openapi.json`.** It is the same API the map
uses: there is no "internal" API richer than the public one.

Rules shared by every route:

- **The hazard** is chosen with `hazard`, which accepts `landslide`, `flood`
  or `wildfire`; when omitted it is `landslide`. Any other value is a `422`.
  Which hazards are active in a given installation is answered by
  `GET /api/hazards`.
- **The classes** are five: `None`, `Low`, `Moderate`, `High`, `VeryHigh`
  (none, low, moderate, high, very high); scores run from 0 to 1.
- **"Not measured" is not "calm".** When a hazard's dynamic signal did not
  arrive (the weather source was down, for instance) the score is 0, like
  that of a quiet cell; to tell them apart, responses carry
  `measured: false`. A client that shows the score without looking at
  `measured` may say "no hazard" where Limen says "I don't know".
- **Degradation.** When an external source is missing, read routes still
  answer `200` with an empty field (`null` or `[]`), never with an error; a
  `404` means the cell, municipality or region does not exist.
- **Caching.** Many routes declare `Cache-Control` (from 30 seconds to a
  day): the data changes at most once an hour, so polling more often brings
  nothing new.
- **Language.** Routes have no language parameter: texts come with the
  language as a suffix (`briefing_it`, `briefing_en`).

Example:

```
curl -s 'http://127.0.0.1:8080/api/aoi/it-puglia/risk/latest?hazard=flood'
```

### Territory and hazards

| Route | What it returns |
|---|---|
| `GET /api/aoi` | The monitored areas (`id`, `name`, `kind`): one per region. |
| `GET /api/hazards` | The hazards this installation can score (`hazard`, `label_it`) and the default one. |
| `GET /api/legend?hazard=` | The five classes with their score bounds (`lo`, `hi`), the matching alert level and the model card. The thresholds come from the hazard's YAML, they are not written in the client. |

### Risk per area and per cell

| Route | What it returns |
|---|---|
| `GET /api/aoi/{aoi_id}/risk/latest?hazard=` | A region's latest assessment: every cell with score, class and breakdown, the counts per class and the narrative (`briefing_it`/`briefing_en`). `briefing_is_fallback: true` means the text is the deterministic one, not the one written by the AI. `404` if the region has no assessment yet for that hazard. |
| `GET /api/cell/{cell_id}/breakdown?hazard=` | A cell's current state: score, class, the factors that make it up, explanation and `measured`. |
| `GET /api/cell/{cell_id}/multi-hazard` | All three hazards together for one cell: the worst, how many are at least moderate and how many at least high, and the detail of each. |
| `GET /api/cell/{cell_id}/history?hazard=&hours=72` | The cell's observed series (last `hours` hours) and forecast series (+24/48/72 h). An unknown cell gives two empty lists, not a `404`. |
| `GET /api/cell/{cell_id}/rain-outlook` | Rain forecast for the next 48 hours: total in mm and hourly peak. `outlook: null` if the weather source does not answer. |
| `GET /api/cell/{cell_id}/rain-models` | Rain over the next 72 hours according to five different weather models (ICON, Météo-France, ECMWF IFS, GFS, ECMWF AIFS), from driest to wettest: how much the models agree. |
| `GET /api/cell/{cell_id}/fwi-normale?fwi=&month=` | How unusual a Fire Weather Index (FWI) value is for that month at that spot: percentile, median and 90th percentile of the local climatology. `normale: null` where there is no climatology. |

### Municipalities and regions

| Route | What it returns |
|---|---|
| `GET /api/comuni?hazard=&aoi=&q=&order=now&limit=50` | The municipalities (comuni) to watch, most urgent first: for each, the worst class, per-hazard details, the +24/48/72 h forecast, the day's official warning if imported, and the attention index (`attention`). Only municipalities at least moderate are listed, unless searching by name with `q`. With `hazard`, threshold and order look at that hazard only; with `order=forecast` the order follows the forecast. |
| `GET /api/comune/{istat_code}` | One municipality with its cells. `404` if the ISTAT code does not exist. |
| `GET /api/comune/{istat_code}/geometry` | The municipality's boundary as GeoJSON. |
| `GET /api/comune/{istat_code}/history?hours=168` | Observed and forecast series per hazard, for the trend charts. |
| `GET /api/regioni` | The picture per region, most to watch first: hazards, forecast, municipalities, today's and tomorrow's official warning, and the narrative per hazard with its translations. |
| `GET /api/regioni/rapporto.pdf?aoi=` | The PDF report for one region, or for all of them without `aoi`. Every page carries the Copernicus attribution. |

A municipality's attention index is the highest among the *measured*
hazards, with a bump when several hazards are above threshold together: it
is not a sum, and an unmeasured hazard does not lower it. If no hazard is
measured, `attention` is `null`, not zero.

### Alerts and forecast

| Route | What it returns |
|---|---|
| `GET /api/alerts?hazard=&threshold=High&since_hours=72&limit=200` | Cells at that class or above, ordered by priority (score weighted by exposure: homes, roads, services), with the municipality name. An unrecognised threshold is read as `High`. |
| `GET /api/alerts/forecast?hazard=&since_hours=72&limit=50` | The forecast notices that were sent: region, hazard, horizon, maximum class, cells involved and text. Without `hazard`, all hazards. |
| `GET /api/alerts/forecast/schedule` | When the next per-cell forecast runs and when the last one ran for each hazard. |

### Explanations and provenance

| Route | What it returns |
|---|---|
| `GET /api/aoi/{aoi_id}/spiegazione?hazard=` | The AI narrative for a region: text, model, time it was written, analysis. `spiegazione: null` when there is none, or when the model did not answer: the deterministic fallback text is never attributed to the AI. |
| `GET /api/report/national?hazard=` | The aggregated national picture: totals, highest-risk cells, a section for each hazard and cascades between hazards. `hazard` picks the hazard that leads the totals. |
| `GET /api/provenienza` | Where the numbers come from *in this installation*: which engine scores, whether the ML challenger runs in shadow, which weather model and which language model writes the narratives. It is configuration read live, not a description. |

### Diagnostics and health

| Route | What it returns |
|---|---|
| `GET /api/status/jobs` | The latest national hourly run (start, end, outcome, duration) and the status per region. |
| `GET /api/shadow/summary?aoi=&since=` | How far the ML challenger diverges from the champion engine, per region, and the comparison on real events. `since` in ISO 8601. The challenger never drives alerts. |
| `GET /api/shadow/reliability?aoi=&since=` | The challenger's reliability curve. `sufficient: false` when there are too few real events to draw it. |
| `GET /health` | Always `200`; `status: degraded` if the database or the cache do not answer. |
| `GET /ready` | `503` until the API is ready: meant for the container orchestrator. |

### Sending a contribution

`POST /api/contributi` is the only public route that accepts data: a report
about a cell (an unrecorded landslide, an opinion on the assessment, on the
weights or the thresholds, a mitigation). The body is JSON with `cell_id`,
`tipo`, `testo` (20 to 4,000 characters), an email and a name or a LinkedIn
profile, and explicit consent; an unknown field is a `422`. The
contribution **is not stored**: it goes by email to the project's curators,
with the cell's current state, and the `201` arrives only after it has been
sent. Submissions are limited per address and in total every hour (beyond
the limit, `429`); without a mail server configured the route answers
`503`. A contribution never changes a score.

## Vector tiles

**The map is made of vector tiles (Mapbox Vector Tile) served by
pg_tileserv straight from the database: anyone can draw the same cells in
another map.** Each source is a SQL view or function; the path is
`/{source}/{z}/{x}/{y}.pbf`, with parameters in the query string.

| Source | Parameters | Properties of each feature |
|---|---|---|
| `public.v_risk_tiles` | — (landslide only) | `cell_id`, `aoi_id`, `risk_score`, `risk_level`, `computed_at`, `measured` |
| `public.risk_at` | `p_hazard` (default `landslide`), `hours_ago` (default 0) | `cell_id`, `risk_score`, `risk_level`, `measured` |
| `public.multi_hazard_at` | none | `cell_id`, `worst_hazard`, `worst_level`, `worst_score`, `measured`, `hazards_scored`, `hazards_at_high` |
| `public.forecast_at` | `p_horizon` (24, 48 or 72; default 24), `p_hazard` (empty = the worst) | `cell_id`, `risk_score`, `risk_level`, `worst_level`, `worst_hazard`, `target_at` |
| `public.v_region_tiles` | — (landslide only) | `aoi_id`, `name`, `cells`, `moderate`, `high_or_above`, `max_score`, `risk_level` |
| `public.v_comune_tiles` | — | `istat_code`, `name`, `worst_hazard`, `worst_class`, `max_score`, `attention`, `measured` |
| `public.v_dpc_allerte_oggi` | — | `zona`, `livello` (0 green … 3 red), `emesso`: the day's official warning |

Three things to know to use them well:

- `risk_at` with `hours_ago` above zero reads the past: that is how the map
  scrolls back in time.
- `forecast_at` contains **only cells at least moderate**: a missing cell is
  not "calm", it is below threshold in the forecast.
- Cells with `measured: false` should be drawn like unassessed ones (the map
  uses the same grey), not with the colour of the lowest class.

The API also offers a proxy, `GET /api/tiles/{layer}/{z}/{x}/{y}.pbf`,
which forwards `p_hazard`, `hours_ago` and `properties`. The proxy does not
forward `p_horizon`: to choose the forecast horizon, query pg_tileserv
directly. If pg_tileserv is not configured the proxy answers `503`, if it
cannot be reached `502`.

## MCP — asking Limen for data and actions

The [Model Context Protocol](https://modelcontextprotocol.io) exposes Limen
as "tools" that a gateway (OpenClaw, Claude Desktop, …) can call. There are
two MCP servers; both speak `stdio` by default and streamable HTTP with
`--transport http`.

### `limen-ops` · `http://127.0.0.1:8766/mcp`

Started with `limen mcp-serve --transport http`; host and port are changed
with `LIMEN_MCP_HTTP_HOST` and `LIMEN_MCP_HTTP_PORT`. The `hazard`
parameter, where present, takes the same values as the API and defaults to
`landslide`.

Read tools (open):

| Tool | What it does |
|---|---|
| `tool_hazards()` | The hazards this installation can score: call it before passing `hazard`. |
| `tool_risk_summary(aoi_id?, hazard?)` | Latest assessment per region: cells scored, cells at least moderate and at least high, maximum score. |
| `tool_top_risk_cells(limit?, aoi_id?, hazard?)` | Ranking of the highest-risk cells (default 10, at most 100). |
| `tool_cell_breakdown(cell_id, hazard?)` | Factor breakdown + explanation of a cell. |
| `tool_recent_alerts(threshold?, since_hours?, limit?, hazard?)` | Cells above threshold in the recent window (default `Moderate`, 24 hours, 50 cells). |
| `tool_multi_hazard_summary(cell_id?, aoi_id?)` | All three hazards together for a cell or a region: give only one of the two. |
| `tool_comune_risk(istat_code)` | A municipality's picture across all hazards, with the attention index. |
| `tool_top_comuni(limit?, aoi_id?)` | The municipalities to watch, ordered by attention (default 10). |
| `tool_national_report()` | Aggregated national picture + ready-made text in `report_it` and `report_en`; accepts `hazard` to choose the hazard that leads the totals. |

Write tools (enabled only by `MCP_ADMIN_TOKEN`: variable unset ⇒
disabled, and the tool answers with an error instead of acting):

| Tool | What it does |
|---|---|
| `tool_run_monitor(aoi_id, admin_token)` | Runs the monitoring workflow once (also accepts `cell_limit` and `hazard`). |
| `tool_build_report(admin_token)` | Builds the static HTML report on demand (idempotent). |
| `tool_forecast_history(admin_token, aoi_ids?)` | Stores the forecast trend (+24/48/72h) for the UI charts. |

### `ispra-geo` · `http://127.0.0.1:8765/mcp` (geodata profile)

ISPRA geographic data (PAI / IFFI). Active only on the VPS, started with
`limen geodata mcp --transport http`:

| Tool | What it does |
|---|---|
| `tool_hazard_at(lat, lon)` | PAI hazard class + authority + region at a point. |
| `tool_iffi_query(bbox or region, movement_type?, limit?)` | Landslides of the IFFI inventory in an area (only one of `bbox` and `region`; at most 500). |
| `tool_pai_summary(region / bbox)` | Area/count distribution per PAI class. |
| `tool_dataset_status()` | Status of the loaded ISPRA datasets: origin, last update, rows. |
| `tool_refresh(dataset, admin_token)` | Reloads a dataset (admin, fail-closed). |

Registering in a gateway:

```
openclaw mcp set limen-ops \
  '{"url":"http://127.0.0.1:8766/mcp","transport":"streamable-http"}'
```

## A2A — interoperability between agents

The [Agent2Agent](https://a2a-protocol.org) protocol lets third-party
agents discover and use Limen in a standard way. The capability card
(Agent Card) is published at:

```
GET /.well-known/agent-card.json
```

(`/.well-known/agent.json` is an alias for older clients.) It declares
`streaming: true` and `pushNotifications: true`, and the available skills
(the same read queries as `limen-ops`; write actions stay on MCP only):

| Skill | What it does |
|---|---|
| `national_report` | National summary (default when no skill is given). |
| `risk_summary` | Summary per region (params `aoi_id`, `hazard`). |
| `top_risk_cells` | Highest-risk cells (params `limit`, `aoi_id`, `hazard`). |
| `cell_breakdown` | Breakdown of a cell (params `cell_id`, `hazard`). |
| `recent_alerts` | Recent alerts (params `threshold`, `since_hours`, `limit`, `hazard`). |
| `top_comuni` | Municipalities to watch (params `limit`, `aoi_id`). |
| `comune_risk` | A municipality's picture (param `istat_code`). |

The JSON-RPC 2.0 endpoint is `POST /a2a`. A skill is selected with a
`DataPart` (or in the message `metadata`); with nothing, or with an unknown
skill, the server answers with the national picture:

```
POST /a2a
{
  "jsonrpc": "2.0", "id": "1", "method": "message/send",
  "params": {
    "message": {
      "role": "user", "messageId": "m1",
      "parts": [{ "kind": "data",
        "data": { "skill": "risk_summary", "params": { "aoi_id": "it-puglia" } } }]
    }
  }
}
```

For incremental updates use `message/stream` (Server-Sent Events, the full
task sequence):

```
POST /a2a   method: "message/stream"   (same params)
→ text/event-stream:
  data: {"result":{"kind":"task","status":{"state":"submitted"}}}
  data: {"result":{"kind":"status-update","status":{"state":"working"}}}
  data: {"result":{"kind":"artifact-update","artifact":{...}}}
  data: {"result":{"kind":"status-update","status":{"state":"completed"},"final":true}}
```

The result arrives as a `DataPart`; when a ready-made text exists
(`report_it`) a `TextPart` precedes it. Other methods: `tasks/get` and
`tasks/cancel` (polling and cancellation), `tasks/pushNotificationConfig/set`
and `/get` to be notified through a webhook when the task ends: Limen sends
the full task to the given URL, with the token as `Authorization:
Bearer`.

## Push notifications

**When an hourly run finds cells above threshold, Limen can warn on its
own, without anyone querying it.** There are four channels: Telegram, MQTT,
email and webhook; they are switched on by listing them in
`NOTIFICATIONS__ENABLED_CHANNELS` and configuring each with its own
`NOTIFICATIONS__TELEGRAM__*`, `__MQTT__*`, `__EMAIL__*`, `__WEBHOOK__*`
variables. With no channel listed, nothing is sent.

What decides whether a notice goes out:

- **the threshold**: at least `Moderate` by default (`ALERT__MIN_LEVEL`);
  below `High` a cell must also have a ground susceptibility of at least
  0.5, because a moderate on stable ground is not news;
- **no repeats**: the same cell is not notified again within 180 minutes
  (`ALERT__DEDUP_WINDOW_MINUTES`); forecast notices are not repeated for the
  same region and horizon within 24 hours;
- **no bursts**: at most 6 messages an hour per channel; the extra ones are
  folded into a digest. A `VeryHigh` always goes through, immediately;
- **per municipality**: cells are grouped by municipality, so the message
  says *where* instead of listing cell codes.

The notice text is **deterministic**: built from the engine's numbers, with
no language model in the path. A notice does not invent figures and does
not change its wording from one day to the next when the data are the same.

The webhook sends `{"text", "message", "payload"}`: `text` and `message`
are the same Italian summary (for OpenClaw's `/hooks/wake` and
`/hooks/agent` hooks), `payload` is the full notice — region, hazard,
maximum class and score, cells with priority and municipality, summary per
municipality, any cascades between hazards and a link to the map.

## Open data and licences

**Limen's code is released under EUPL-1.2; the data it uses keep their
sources' licences, and whoever republishes what Limen produces carries the
same attributions along.** The main ones:

| Source | Licence |
|---|---|
| ISPRA IdroGEO (PAI, IFFI, flood hazard) | CC-BY 4.0 |
| Open-Meteo (forecasts and ERA5 archive) | CC-BY 4.0 |
| INGV (earthquakes) | CC-BY 4.0 |
| Protezione Civile (Italy's civil-protection department; warning bulletins) | CC-BY 4.0 |
| ISTAT boundaries | CC-BY 4.0 |
| CORINE Land Cover | CC-BY |
| OpenStreetMap | ODbL |
| GloFAS and EFAS (Copernicus CEMS-Floods) | CEMS licence, with mandatory wording |

**For floods the Copernicus wording is mandatory.** Every surface showing
flood scores derived from GloFAS must state: "Contains modified Copernicus
Emergency Management Service information [Year]" (in Italian: «Contiene
informazioni modificate del Copernicus Emergency Management Service,
[anno]»), and must not present the result as a flood warning: issuing
warnings is the responsibility of national and regional authorities. The
PDF report and the map already carry it; whoever integrates the API or the
tiles into another application must add it.

The full list, with each source's conditions, is in the
[README](https://github.com/agent-engineering-studio/limen/blob/main/README.md#attribution-and-open-licences).

## Quick setup

The idempotent script
[scripts/setup_openclaw.sh](https://github.com/agent-engineering-studio/limen/blob/main/scripts/setup_openclaw.sh)
registers both MCP servers, enables the gateway's notification hooks, sends
a test message and prints the lines to add to Limen's configuration for the
webhook channel, together with the Agent Card URL. Full guide and
troubleshooting:
[docs/openclaw.md](https://github.com/agent-engineering-studio/limen/blob/main/docs/openclaw.md).

## Security and guarantees

- **No integration changes a score.** API, tiles, read tools and A2A skills
  read what the engine has already written.
- **Write actions are fail-closed.** They require `MCP_ADMIN_TOKEN`; if the
  variable is not set, they are off.
- **No language model in the notices.** Notification texts are
  deterministic; the AI only writes the narratives, which are marked as
  such.
- **Ports published by the containers bind to loopback by default.** Public
  exposure goes through a reverse proxy on HTTPS; the MCP servers must not
  be exposed without one.
- **No personal data kept.** The only route that receives data from a
  visitor, the contributions one, forwards it by email and does not store
  it.
