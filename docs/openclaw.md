# Limen ⇄ OpenClaw — guida di integrazione

> Come collegare Limen a un gateway agentico [OpenClaw](https://docs.openclaw.ai)
> per interrogare il rischio frane in linguaggio naturale e reagire in
> automatico agli alert. Tutto il lato Limen è **già implementato e attivo**;
> questa guida copre la configurazione da fare quando il server esiste.
> Setup rapido: [`scripts/setup_openclaw.sh`](../scripts/setup_openclaw.sh).

## Architettura

Due canali complementari, entrambi parametrici via env (stesso host oggi,
VPS dedicato domani — cambia solo un URL):

```
                 pull (domande)                        push (eventi)
  OpenClaw ──── MCP streamable-http ────▶ limen-ops   Limen ──── POST /hooks ────▶ OpenClaw
  "che rischio c'è in Puglia?"            :8766/mcp   alert operativi, PREVISIONE,  :18789
                                                      report nazionale mattutino
```

1. **Pull — MCP `limen-ops`**: l'agente interroga Limen on-demand.
   Il servizio compose `mcp` (immagine `limen/mcp:0.1`) espone HTTP
   streamable su `127.0.0.1:8766/mcp`. Tool disponibili:

   | Tool | Cosa restituisce |
   |---|---|
   | `tool_risk_summary(aoi_id?)` | ultimo assessment per regione (celle per classe, punteggio max) |
   | `tool_top_risk_cells(limit?, aoi_id?)` | classifica nazionale delle celle a rischio più alto |
   | `tool_cell_breakdown(cell_id)` | scomposizione S/M/E/F/H/K + briefing italiano di una cella |
   | `tool_recent_alerts(threshold?, since_hours?, limit?)` | celle sopra soglia nella finestra recente |
   | `tool_national_report()` | quadro nazionale aggregato + testo pronto in `report_it` |
   | `tool_run_monitor(aoi_id, admin_token)` | lancia il workflow (admin; fail-closed senza `MCP_ADMIN_TOKEN`) |

2. **Push — canale di notifica `webhook`**: quando Limen genera un evento
   (alert operativo, alert **PREVISIONE** a +48h, report nazionale delle 06 UTC)
   fa POST al gateway hooks di OpenClaw. Il body contiene `text` e `message`
   (il riassunto deterministico in italiano — i campi che `/hooks/wake` e
   `/hooks/agent` rispettivamente richiedono) più `payload` con l'alert completo.

Il pattern d'uso tipico: l'alert *sveglia* l'agente via webhook → l'agente
chiama `tool_cell_breakdown` via MCP per capire il perché → compone un
messaggio ricco e lo consegna sul canale che usi (WhatsApp/Telegram/…).

## Prerequisiti

- Stack Limen su (`make up`): il servizio `limen-mcp` deve rispondere —
  `docker ps | grep limen-mcp`.
- OpenClaw installato con gateway attivo (porta default **18789**).
- Se OpenClaw sta su un'**altra macchina**: vedi [Topologia remota](#topologia-remota).

## Setup in 3 passi

### 1. Lancia lo script (sulla macchina del gateway)

```bash
# default: tutto same-host
./scripts/setup_openclaw.sh

# oppure parametrizzato:
LIMEN_MCP_URL=http://127.0.0.1:8766/mcp \
OPENCLAW_GATEWAY_URL=http://127.0.0.1:18789 \
OPENCLAW_HOOK_MODE=wake \
OPENCLAW_HOOK_TOKEN=il-tuo-secret \
./scripts/setup_openclaw.sh
```

Lo script è idempotente: registra l'MCP (`openclaw mcp set limen-ops …`),
abilita gli hooks (o stampa lo snippet JSON5 da incollare nel config del
gateway se la CLI non lo supporta), verifica l'endpoint con un POST di test
e stampa le righe `.env` per il lato Limen.

Variabili accettate:

| Variabile | Default | Significato |
|---|---|---|
| `LIMEN_MCP_URL` | `http://127.0.0.1:8766/mcp` | endpoint MCP di Limen visto dal gateway |
| `OPENCLAW_GATEWAY_URL` | `http://127.0.0.1:18789` | base URL del gateway OpenClaw |
| `OPENCLAW_HOOK_TOKEN` | generato (`openssl rand`) | shared secret degli hooks |
| `OPENCLAW_HOOK_MODE` | `wake` | `wake` = evento alla sessione principale; `agent` = turno agente isolato |
| `MCP_SERVER_NAME` | `limen-ops` | nome dell'MCP dentro OpenClaw |

### 2. Configura il lato Limen

Nel `.env` di Limen (lo script stampa le righe esatte):

```bash
NOTIFICATIONS__ENABLED_CHANNELS=["webhook"]        # + telegram/mqtt se già in uso
NOTIFICATIONS__WEBHOOK__URL=http://127.0.0.1:18789/hooks/wake
NOTIFICATIONS__WEBHOOK__TOKEN=<lo stesso token degli hooks>
```

Poi `make up` (ricrea l'api con il canale attivo).

### 3. Verifica end-to-end

```bash
# MCP: l'agente vede i tool?
openclaw mcp status limen-ops --verbose

# push: simula un alert Limen → OpenClaw
curl -X POST http://127.0.0.1:18789/hooks/wake \
  -H "Authorization: Bearer $OPENCLAW_HOOK_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"text":"Prova alert Limen"}'

# pull: chiedi all'agente "situazione frane in Italia oggi"
# → deve chiamare tool_national_report e risponderti col quadro reale
```

## Scelta `wake` vs `agent`

- **`/hooks/wake`** (default): l'evento entra nella sessione principale
  dell'agente — buono per un assistente personale che tiene il filo.
- **`/hooks/agent`**: ogni alert lancia un turno isolato (campo `message`,
  opzionali `name`, `model`, `deliver`, `channel`, `to`) — buono per
  automazioni pure, es. "inoltra su WhatsApp arricchendo con l'MCP".
  Cambia solo l'URL: `NOTIFICATIONS__WEBHOOK__URL=…/hooks/agent`.

Il body inviato da Limen contiene sempre entrambi i campi (`text` e
`message`), quindi l'URL è l'unica cosa da cambiare.

## Topologia remota

Quando OpenClaw vive su un VPS dedicato:

| Direzione | Cosa cambia |
|---|---|
| OpenClaw → MCP Limen | sul server Limen: `LIMEN_MCP_BIND=0.0.0.0` nel `.env` (il compose pubblica `:8766` fuori dal loopback) **solo dietro reverse-proxy TLS**; poi `LIMEN_MCP_URL=https://limen.example.com/mcp` nello script |
| Limen → hooks OpenClaw | esporre il gateway dietro TLS e usare `NOTIFICATIONS__WEBHOOK__URL=https://openclaw.example.com/hooks/wake` |

Le raccomandazioni ufficiali OpenClaw: hooks dietro loopback, tailnet o
reverse-proxy fidato; token dedicato, mai riusare credenziali del gateway.

## Sicurezza

- `MCP_ADMIN_TOKEN` **non impostato** ⇒ `tool_run_monitor` è disabilitato
  (fail-closed). Impostalo solo se vuoi che gli agenti possano lanciare run.
- Il token hooks viaggia come `Authorization: Bearer` — mai in query string
  (OpenClaw li rifiuta comunque).
- I tool MCP di lettura non alterano mai i punteggi: leggono e basta.
  Gli alert webhook sono testo deterministico — nessun LLM nel percorso.

## Troubleshooting

| Sintomo | Causa probabile | Rimedio |
|---|---|---|
| `openclaw mcp status` fallisce la probe | servizio `limen-mcp` giù o URL sbagliato | `docker ps \| grep limen-mcp`; `curl -X POST http://127.0.0.1:8766/mcp` deve rispondere JSON-RPC (anche un errore "Missing session ID" va bene: il server c'è) |
| hook risponde 401 | token diverso tra gateway e `.env` Limen | riallinea `hooks.token` e `NOTIFICATIONS__WEBHOOK__TOKEN` |
| hook risponde 404 | gateway non riavviato dopo la config, o `hooks.path` diverso | riavvia il gateway; verifica `hooks.path` |
| alert Limen non arrivano | canale non abilitato | `NOTIFICATIONS__ENABLED_CHANNELS` deve contenere `"webhook"`; log `webhook.send` nell'api |
| `webhook.send.degraded` nei log | gateway irraggiungibile dal container api | dal container: `docker exec limen-api python -c "import urllib.request; urllib.request.urlopen('http://host.docker.internal:18789')"` — se OpenClaw è sull'host, l'URL nel `.env` deve usare `host.docker.internal`, non `127.0.0.1` |

> **Nota container→host**: il canale webhook parte dal **container** api.
> Se il gateway OpenClaw gira sull'host della stessa macchina, usa
> `NOTIFICATIONS__WEBHOOK__URL=http://host.docker.internal:18789/hooks/wake`.
