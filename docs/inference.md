# Motore di inferenza

Limen non ospita modelli. Parla a **un solo endpoint**: il gateway LiteLLM
sull'host, che fa routing per nome di modello, applica il tetto di spesa e
gestisce il fallback locale→cloud. Puntare i client direttamente a llama-swap
o a colibrì aggira tutte e tre le cose.

```
limen-api (container, rete limen_default 172.19.0.0/16)
   │  LLM__LLAMACPP_BASE_URL=http://host.docker.internal:8091
   ▼
LiteLLM gateway :8091  ──┬── llama-swap :8083   (modelli piccoli, GPU)
                         ├── llama-embed :8082  (embedding)
                         └── colibrì :8070      (GLM-5.2, 400 GB su NVMe)
```

`host.docker.internal` è mappato via `extra_hosts: host-gateway` nei compose.
**Dentro un container `127.0.0.1` è il container stesso**: non raggiunge mai il
gateway.

> `:8081` **non** è un motore LLM su questo host — è GeoServer. Ogni
> riferimento a 8081 come endpoint di inferenza è sbagliato: llama-swap sta su
> 8083, il gateway su 8091.

## Modelli del gateway

Nomi verificati con `GET /v1/models`. Sono chiavi del `model_list` del
gateway, **non** nomi di file: cambiarli lì cambia cosa risponde, senza
toccare Limen.

| Nome | Cos'è | Uso in Limen |
|---|---|---|
| `fast` | 4B, GPU-resident | ruoli senza vincoli di prosa |
| `chat` | 8B, GPU-resident | prosa italiana (briefing) |
| `extract` | profilo JSON (grammar-constrained) | output JSON stretto |
| `embed` | embedding | sidecar KG |
| `quality-local` | colibrì / GLM-5.2 | **vietato** — vedi sotto |
| `quality-cloud` | Claude via API, fallback di `quality-local` nel gateway | — |
| `glm52` | colibrì per nome diretto | **vietato** — vedi sotto |

`glm52` risultava assente dal catalogo all'ultima verifica (il gateway ne
annunciava 6). Resta comunque in denylist: la lista del gateway può cambiare
senza che Limen lo sappia.

## Mappa ruolo → modello

I ruoli sono definiti in `limen.agents.llm_factory.resolver._ROLE_FIELDS` e si
configurano con `LLM__MODELS__<RUOLO>`.

| Ruolo | Env var | Default nel compose | Call site |
|---|---|---|---|
| `RiskAnalyst` | `LLM__MODELS__RISK_ANALYST` | `extract` | `agents/workflows/main_workflow.py:107` |
| `Briefing` | `LLM__MODELS__BRIEFING` | `chat` | `agents/workflows/main_workflow.py:144` |
| `Orchestrator` | `LLM__MODELS__ORCHESTRATOR` | `fast` | *nessuno* |
| `Scorer` | `LLM__MODELS__SCORER` | `fast` | *nessuno* |
| `Summarizer` | `LLM__MODELS__SUMMARIZER` | `fast` | *nessuno* |

Gli ultimi tre sono configurazione dichiarata senza consumatore: `.create()`
viene chiamato solo per `RiskAnalyst` e `Briefing`.

I motori locali (`llamacpp`, `ollama`) onorano **solo i ruoli dichiarati in
environment**. Un ruolo non dichiarato ripiega su `LLM__LLAMACPP_MODEL` /
`LLM__OLLAMA_MODEL`, perché i default del codice sono id Claude che il gateway
rifiuterebbe con un 400. I provider cloud ricevono invece la mappa intera.

## Il vincolo: `quality-local` mai su percorsi sincroni

**Misura reale, non stima: una richiesta a colibrì con 3 token di output ha
richiesto 40 secondi** (≈ 0,08 tok/s a cache fredda). Poche centinaia di token
sono decine di minuti.

Ogni ruolo di `LLM__MODELS__*` è invocato su un percorso sincrono:

| Punto d'ingresso | File:riga | Intervallo / attesa |
|---|---|---|
| `POST /api/monitor/{aoi_id}` | `api/endpoints/monitor.py:33-40` | il client HTTP resta appeso |
| tool MCP `run_monitor` | `mcp/tools.py:188-190` | l'agente resta appeso |
| trigger nowcast radar | `api/jobs/nowcast_monitoring.py:69-75` | **15 min** |
| trigger FIRMS | `api/jobs/firms_monitoring.py:70-76` | 45 min |
| sweep oraria | `api/jobs/hourly_monitoring.py:60-68` | 60 min |
| `limen monitor-once` | `cli/monitor_once.py:60` | foreground |

Il caso peggiore non è la richiesta HTTP: è la **sweep oraria**. Il loop a
`hourly_monitoring.py:61` è sequenziale su tutte le AOI, e
`run_hourly_monitoring` è protetta da `_sweep_lock` che **scarta** i tick
successivi. Con un briefing da decine di minuti la prima sweep non chiude
entro l'ora, ogni tick seguente logga `job.hourly_monitoring.skip`, e il
monitoraggio nazionale si ferma. Nessun errore, nessun alert: solo un sistema
che sembra vivo e non sta più valutando niente.

Per questo il vincolo è **imposto per costruzione, non per convenzione**:
`limen.config.settings.SLOW_GENERATION_MODELS` elenca i modelli vietati e un
`model_validator` su `LLMSettings` **rifiuta di far partire il processo** se un
ruolo ci è mappato. Copre anche le chiavi non previste (`LLMModels` ha
`extra="allow"`), quindi un futuro `LLM__MODELS__REPORT=quality-local` non
passa di straforo. È lo stesso principio per cui colibrì rifiuta di ascoltare
su `0.0.0.0` senza chiave: meglio un errore chiaro che un degrado silenzioso.

### Come si userà colibrì (proposta, non implementata)

Un modello che genera in decine di minuti non è inutile — è un modello *batch*.
Serve un percorso che non abbia mai un client in attesa:

1. Un ruolo dedicato (`report` / `deep_analysis`) fuori da `LLM__MODELS__*`,
   con la propria allowlist che ammette `quality-local`.
2. Un job asincrono che lo invoca, sul modello di `api/jobs/daily_report.py`:
   nessun intervallo breve, nessun lock condiviso con la sweep.
3. Esito **persistito** (tabella o object store) con stato
   `pending`/`done`/`failed`, recuperabile da un endpoint che legge il record
   e risponde subito — mai un endpoint che attende la generazione.
4. Tetto per-ruolo generoso (`LLM__LLAMACPP_ROLE_TIMEOUT_SECONDS`), senza
   toccare quello globale.

Finché questo non esiste, la validazione all'avvio è la protezione.

## Timeout

`LLM__LLAMACPP_TIMEOUT_SECONDS` (default **120 s**) è il tetto per i ruoli
senza override. `LLM__LLAMACPP_ROLE_TIMEOUT_SECONDS` è un JSON chiavato
sull'etichetta del ruolo:

```
LLM__LLAMACPP_ROLE_TIMEOUT_SECONDS={"Briefing": 5400}
```

Un tetto **troppo alto danneggia quanto uno troppo basso**, al contrario.
Troppo basso taglia un modello sano a metà risposta. Troppo alto rende un
motore *rotto* indistinguibile da uno lento per tutta la durata del tetto: il
chiamante si blocca, scade, ripiega comunque sul percorso deterministico, e
l'unica cosa che l'attesa in più ha comprato è che te ne accorgi più tardi.
Il numero risponde a «quanto può plausibilmente metterci un modello che
funziona», non a «quanto siamo disposti ad aspettare».

Sulla Z8 con i GGUF su NVMe: ~8 s alla prima richiesta (caricamento), poi
0,1–0,2 s. 120 s ha margine ampio.

## Diagnostica

```bash
uv run limen llm-check                          # da host
docker compose exec api limen llm-check         # da dentro il container
```

Stampa provider, base URL, catalogo del gateway e — per ogni ruolo — il
modello risolto, se viene da `LLM__MODELS__*` (`declared`) o dal ripiego
(`fallback`), il tetto applicato e la latenza di un round trip reale. Esce
non-zero se un ruolo non risponde, quindi vale anche come gate di deploy.
Eseguirlo **dentro** il container non è pedanteria: da host `127.0.0.1`
funziona e dal container no, quindi una verifica da host non dice niente su
cosa vede il processo API.

Un `ok` con risposta vuota è normale: il probe verifica che la rotta risolva e
che la risposta sia parsabile, e con un modello reasoning il budget di token
può finire tutto nei think-token.

### Il segnale nei log

Quando un ruolo non risponde, Limen **non** va in errore: ripiega sul testo
deterministico, che è l'invariante (`gli alert non inventano cifre`). L'unico
modo per scoprirlo è l'evento dedicato:

```
llm.fallback   role=Briefing   reason=chat error: ConnectError
```

Sempre `warning`, mai `info`, ed emesso da un solo punto per agente
(`_neutral_fallback` in `risk_analyst.py`, `_fallback_briefing` in
`briefing.py`) così che un grep li trovi tutti. Un ciclo che lo emette ha
prodotto un'analisi *degradata* pur sembrando normale.

## Gli altri servizi

| Servizio | Provider | Variabili |
|---|---|---|
| `limen-api` | `llamacpp` | `LLM__LLAMACPP_*`, `LLM__MODELS__*` |
| `knowledge-graph` | `llamacpp` | `KG_LLM_PROVIDER`, `LLAMACPP_BASE_URL`, `LLAMACPP_EXTRACTION_MODEL`, `EMBEDDING_PROVIDER`, `LLAMACPP_EMBEDDING_*` |
| `geoserver-webui` | `openai` | `GEO_LLM_PROVIDER=openai`, `OPENAI_BASE_URL`, `OPENAI_LLM_MODEL` |
| `geoserver-mcp` | `openai` | idem |

I due servizi GeoServer vivono in `mcp-geo-server`, i cui provider `ollama` e
`ollama-cloud` parlano il protocollo Ollama nativo (`/api/chat`): puntare
`OLLAMA_HOST` al gateway falliva sull'URL, prima ancora del modello. Per
questo usano il provider `openai`, aggiunto in quel repo — un client
OpenAI-compatibile con `base_url` esplicito.

`OPENAI_BASE_URL` per quei due **include il suffisso `/v1`** (l'SDK OpenAI
accoda solo il path), mentre `LLM__LLAMACPP_BASE_URL` **no** (il client di
Limen accoda `/v1/chat/completions` da sé). Differenza reale, non un typo.

Le immagini `mcp-geo-server` sono **pullate da GHCR**: una modifica al
sorgente ha effetto solo dopo rebuild e publish dell'immagine, o passando
un'immagine locale con `GEOSERVER_APP_IMAGE` / `GEOSERVER_BOOTSTRAP_IMAGE`.

Per il sidecar KG gli embedding **non** sono liberamente sostituibili:
l'indice vettoriale Redis è dimensionato sulla larghezza del modello
(`REDIS_VECTOR_DIM`, 1024 per Qwen3-Embedding-0.6B). Cambiare modello vuol
dire ricostruire l'indice e re-ingestare.
