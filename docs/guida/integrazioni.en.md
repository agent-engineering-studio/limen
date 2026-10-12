# Integrations: MCP & A2A

**Other systems can query Limen in two complementary ways: through MCP (an
agent gateway asks for data and actions) and through A2A (standard
agent-to-agent interoperability, with streaming and push notifications).**
Both are read-only with respect to the score: no integration can alter a
risk value.

## MCP — asking Limen for data and actions

The [Model Context Protocol](https://modelcontextprotocol.io) exposes Limen
as "tools" that a gateway (OpenClaw, Claude Desktop, …) can call. There are
two MCP servers.

### `limen-ops` · `http://127.0.0.1:8766/mcp`

Read tools (open):

| Tool | What it does |
|---|---|
| `tool_risk_summary(aoi_id?)` | Latest assessment per region: cells per class, maximum score. |
| `tool_top_risk_cells(limit?, aoi_id?)` | Ranking of the highest-risk cells. |
| `tool_cell_breakdown(cell_id)` | S/M/E/F/H/K breakdown of a cell, plus its briefing. |
| `tool_recent_alerts(threshold?, since_hours?, limit?)` | Cells above threshold in the recent window. |
| `tool_national_report()` | Aggregated national picture, with ready-made text in `report_it`. |

Write tools (enabled only by `MCP_ADMIN_TOKEN`: variable unset ⇒
disabled):

| Tool | What it does |
|---|---|
| `tool_run_monitor(aoi_id, admin_token)` | Runs the monitoring workflow once. |
| `tool_build_report(admin_token)` | Builds the static HTML report on demand (idempotent). |
| `tool_forecast_history(admin_token, aoi_ids?)` | Stores the forecast trend (+24/48/72h) for the UI charts. |

### `ispra-geo` · `http://127.0.0.1:8765/mcp` (geodata profile)

ISPRA geographic data (PAI / IFFI). Active only on the VPS:

| Tool | What it does |
|---|---|
| `tool_hazard_at(lat, lon)` | PAI hazard class + authority + region at a point. |
| `tool_iffi_query(...)` | Landslides of the IFFI inventory in an area. |
| `tool_pai_summary(region / bbox)` | Area/count distribution per PAI class. |
| `tool_dataset_status()` | Status of the loaded ISPRA datasets. |
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

It declares `streaming: true` and `pushNotifications: true`, and the
available skills (the same queries as `limen-ops`):

| Skill | What it does |
|---|---|
| `national_report` | National summary (default when no skill is given). |
| `risk_summary` | Summary per region (param `aoi_id`). |
| `top_risk_cells` | Highest-risk cells (params `limit`, `aoi_id`). |
| `cell_breakdown` | Breakdown of a cell (param `cell_id`). |
| `recent_alerts` | Recent alerts (params `threshold`, `since_hours`, `limit`). |

The JSON-RPC 2.0 endpoint is `POST /a2a`. A skill is selected with a
`DataPart` (or in the message `metadata`); with nothing, the server
answers with the national picture:

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

Other methods: `tasks/get` and `tasks/cancel` (polling and cancellation),
`tasks/pushNotificationConfig/set` to be notified through a webhook when
the task ends.

## Quick setup

The idempotent script
[scripts/setup_openclaw.sh](https://github.com/agent-engineering-studio/limen/blob/main/scripts/setup_openclaw.sh)
registers both MCP servers, enables the notification hooks and prints the
Agent Card URL. Full guide and troubleshooting:
[docs/openclaw.md](https://github.com/agent-engineering-studio/limen/blob/main/docs/openclaw.md).

> Security: read tools and A2A skills never alter scores. Write actions
> require `MCP_ADMIN_TOKEN` (fail-closed). Push alerts are deterministic
> text, with no LLM in the path.
