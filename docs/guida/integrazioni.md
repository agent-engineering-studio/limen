# Integrazioni: MCP & A2A

**Limen si lascia interrogare da altri sistemi in due modi complementari:
via MCP (un gateway agentico chiede dati e azioni) e via A2A
(interoperabilità standard tra agent, con streaming e notifiche push).**
Entrambi sono di sola lettura sul punteggio: nessuna integrazione può
alterare un valore di rischio.

## MCP — chiedere dati e azioni a Limen

Il [Model Context Protocol](https://modelcontextprotocol.io) espone Limen
come «strumenti» che un gateway (OpenClaw, Claude Desktop, …) può chiamare.
I server MCP sono due.

### `limen-ops` · `http://127.0.0.1:8766/mcp`

Strumenti di lettura (aperti):

| Strumento | Cosa fa |
|---|---|
| `tool_risk_summary(aoi_id?)` | Ultimo assessment per regione: celle per classe, punteggio max. |
| `tool_top_risk_cells(limit?, aoi_id?)` | Classifica delle celle a rischio più alto. |
| `tool_cell_breakdown(cell_id)` | Scomposizione S/M/E/F/H/K + briefing italiano di una cella. |
| `tool_recent_alerts(threshold?, since_hours?, limit?)` | Celle sopra soglia nella finestra recente. |
| `tool_national_report()` | Quadro nazionale aggregato + testo pronto in `report_it`. |

Strumenti di scrittura (abilitati solo da `MCP_ADMIN_TOKEN`: variabile non
impostata ⇒ disabilitati):

| Strumento | Cosa fa |
|---|---|
| `tool_run_monitor(aoi_id, admin_token)` | Lancia il workflow di monitoraggio una volta. |
| `tool_build_report(admin_token)` | Genera il report HTML statico on-demand (idempotente). |
| `tool_forecast_history(admin_token, aoi_ids?)` | Persiste il trend di previsione (+24/48/72h) per i grafici UI. |

### `ispra-geo` · `http://127.0.0.1:8765/mcp` (profilo geodata)

Dati geografici ISPRA (PAI / IFFI). Attivo solo sul VPS:

| Strumento | Cosa fa |
|---|---|
| `tool_hazard_at(lat, lon)` | Classe di pericolosità PAI + autorità + regione in un punto. |
| `tool_iffi_query(...)` | Frane del catalogo IFFI in un'area. |
| `tool_pai_summary(region / bbox)` | Distribuzione area/conteggio per classe PAI. |
| `tool_dataset_status()` | Stato dei dataset ISPRA caricati. |
| `tool_refresh(dataset, admin_token)` | Ricarica un dataset (admin, fail-closed). |

Registrazione in un gateway:

```
openclaw mcp set limen-ops \
  '{"url":"http://127.0.0.1:8766/mcp","transport":"streamable-http"}'
```

## A2A — interoperabilità tra agent

Il protocollo [Agent2Agent](https://a2a-protocol.org) permette ad agent di
terze parti di scoprire e usare Limen in modo standard. La carta capacità
(Agent Card) è pubblicata su:

```
GET /.well-known/agent-card.json
```

Dichiara `streaming: true` e `pushNotifications: true`, e le skill
disponibili (le stesse query di `limen-ops`):

| Skill | Cosa fa |
|---|---|
| `national_report` | Sintesi nazionale (default se nessuna skill è indicata). |
| `risk_summary` | Sintesi per regione (param `aoi_id`). |
| `top_risk_cells` | Celle a rischio più alto (param `limit`, `aoi_id`). |
| `cell_breakdown` | Scomposizione di una cella (param `cell_id`). |
| `recent_alerts` | Allerte recenti (param `threshold`, `since_hours`, `limit`). |

L'endpoint JSON-RPC 2.0 è `POST /a2a`. Una skill si seleziona con un
`DataPart` (o nei `metadata` del messaggio); senza nulla, il server risponde
con il quadro nazionale:

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

Per aggiornamenti incrementali usa `message/stream` (Server-Sent Events,
sequenza completa del task):

```
POST /a2a   method: "message/stream"   (stessi params)
→ text/event-stream:
  data: {"result":{"kind":"task","status":{"state":"submitted"}}}
  data: {"result":{"kind":"status-update","status":{"state":"working"}}}
  data: {"result":{"kind":"artifact-update","artifact":{...}}}
  data: {"result":{"kind":"status-update","status":{"state":"completed"},"final":true}}
```

Altri metodi: `tasks/get` e `tasks/cancel` (polling e annullamento),
`tasks/pushNotificationConfig/set` per farsi notificare via webhook al
termine del task.

## Setup rapido

Lo script idempotente
[scripts/setup_openclaw.sh](https://github.com/agent-engineering-studio/limen/blob/main/scripts/setup_openclaw.sh)
registra entrambi gli MCP, abilita gli hook di notifica e stampa l'URL della
Agent Card. Guida completa e troubleshooting:
[docs/openclaw.md](https://github.com/agent-engineering-studio/limen/blob/main/docs/openclaw.md).

> Sicurezza: gli strumenti di lettura e le skill A2A non alterano mai i
> punteggi. Le azioni di scrittura richiedono `MCP_ADMIN_TOKEN`
> (fail-closed). Gli alert push sono testo deterministico, senza LLM nel
> percorso.
