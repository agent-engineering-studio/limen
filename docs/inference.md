# Motore di inferenza

Limen non ospita modelli. Parla a **un solo endpoint**: il gateway LiteLLM
sull'host, che fa routing per nome di modello, applica il tetto di spesa e
gestisce il fallback locale→cloud. Puntare i client direttamente a llama-swap
aggira tutte e tre le cose. L'unica eccezione è il revisore di fedeltà, che
manda il suo campione all'API Message Batches di Claude (sotto).

```
limen-api (container, rete limen_default 172.19.0.0/16)
   │  LLM__LLAMACPP_BASE_URL=http://host.docker.internal:8091
   ▼
LiteLLM gateway :8091  ──┬── llama-swap :8083   (modelli piccoli, GPU)
                         ├── llama-embed :8082  (embedding)
                         └── API Anthropic      (fast-cloud, quality-cloud)
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
| `quality-cloud` | Claude Sonnet 5.5 via API | — |
| `fast-cloud` | Claude Haiku 5.5 via API: 0,10 $ / 0,50 $ per milione di token, venti volte meno di Sonnet | `briefing` e `risk_analyst` in produzione |

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

## Il revisore di fedeltà: `fedelta`

Il revisore serale (`api/jobs/fedelta_racconti.py`, CLI `limen
fedelta-racconti`). Una volta per sera, a `LLM__FEDELTA_ORA_UTC` (default 21,
dopo la previsione per cella delle 20:20), rilegge un campione casuale delle
spiegazioni dell'AI delle ultime 24 ore e ne giudica la fedeltà ai dati da cui
sono nate (`spiegazioni_regione.ingresso`, migrazione 069):

* **i numeri**, in modo deterministico (`briefing_eval`): ogni numero del testo
  deve stare nel messaggio che il modello ha ricevuto;
* **il resto**, con un secondo modello: cause attribuite male, luoghi
  inventati, eventi futuri dati per certi.

Il verdetto va in `spiegazioni_regione.fedelta` e, se negativo, in un warning
`racconto.infedele`. Non corregge niente: segnala. Un revisore che non risponde
lascia il giudizio a `null`, mai «fedele».

```bash
LLM__MODELS__FEDELTA=claude-sonnet-5-5
LLM__FEDELTA_CAMPIONE=4
LLM__FEDELTA_ATTESA_MASSIMA_MINUTI=120
```

Non passa dal gateway: tutto il campione va in **un solo Message Batch**
(metà prezzo, nessuno aspetta il verdetto) con l'SDK `anthropic` (gruppo
`agents`, nell'immagine) e `ANTHROPIC_API_KEY`. Il job aspetta che il batch
finisca; oltre l'attesa massima lo annulla e i verdetti restano a `null`. Il
JSON del giudizio è vincolato da uno schema (output strutturati), quindi una
risposta malformata non c'è più — un rifiuto o un `max_tokens` sì, e valgono
`null`.

Sonnet e non Haiku: le spiegazioni le scrive `fast-cloud` (Haiku 5.5), e un
revisore che rilegge sé stesso ha i suoi stessi punti ciechi. Un revisore più
piccolo non basta: Qwen3-8B (`chat`) su 27 spiegazioni ne ha date per non
fedeli 19, quasi tutte per frasi condizionali lette come certezze, e ha
mancato la causa sbagliata che GLM-5.2 aveva trovato (Trentino, 22/10/2026).

Prima girava su GLM-5.2 in locale (colibrì), acceso dalle 20:50 alle 02:05:
venti minuti di prefill per giudizio, 21 GB di RAM di picco, e il 28/10/2026,
acceso di giorno da un timer `Persistent=true` dopo un riavvio, ha mandato
la macchina in OOM e trascinato via `limen`. Sonnet in batch, sui quattro
giudizi a sera, costa circa un dollaro e mezzo al mese. Senza `LLM__MODELS__FEDELTA`
o senza `ANTHROPIC_API_KEY` il job non gira.

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

## Replicare lo stack su un'altra macchina

Su questo server il gateway, llama-swap e l'embedding girano come
unità systemd sull'host. Per portarli altrove c'è un Compose a sé,
`infra/docker/docker-compose.inference.yml` (progetto `limen-inference`), con
le stesse porte e gli stessi nomi di modello:

| Servizio | Immagine | Porta | Note |
|---|---|---|---|
| `litellm` | `ghcr.io/berriai/litellm` | 8091 | config `infra/inference/litellm.yaml` |
| `llama-swap` | `ghcr.io/mostlygeek/llama-swap` (CUDA) | 8083 | config `infra/inference/llama-swap.yaml`, modelli in `$LIMEN_MODELS_DIR/gguf` |
| `llama-embed` | `ghcr.io/ggml-org/llama.cpp:server` | 8082 | CPU |

```bash
cp infra/inference/secrets.env.example infra/inference/secrets.env  # chiavi, mai nel repo
make inference-up            # gateway + llama-swap + embedding
make inference-up-cpu        # senza GPU: gateway + embedding, fast/chat/extract su Claude
make inference-check         # i nomi di modello che il gateway espone
```

**Senza GPU** (#306): `make inference-up-cpu` avvia solo il gateway e
l'embedding (llama.cpp su CPU) con `infra/inference/litellm.cpu.yaml`: stessi
nomi di modello, quindi `LLM__MODELS__*` non cambia, ma `fast`, `chat` ed
`extract` vanno a Claude. Senza `ANTHROPIC_API_KEY` le chiamate falliscono e
Limen pubblica il testo deterministico. llama-swap sta nel profilo `gpu`, che `inference-up` attiva.

Con la GPU servono Docker con NVIDIA Container Toolkit e i modelli in
`LIMEN_MODELS_DIR` (default `/srv/models`): nessun peso entra nelle immagini.
Il gateway si aggancia anche alla rete `limen_default`, quindi dal container
API basta `LLM__LLAMACPP_BASE_URL=http://litellm:4000`. Su questo server le
porte sono già prese dalle unità systemd: fermale prima di avviare il
Compose, o sposta le porte con `LIMEN_*_PORT`.

## Gli altri servizi

| Servizio | Provider | Variabili |
|---|---|---|
| `limen-api` | `llamacpp` | `LLM__LLAMACPP_*`, `LLM__MODELS__*` |
| `kg-api` (repo esterno) | `llamacpp` | `KG_LLM_PROVIDER`, `LLAMACPP_BASE_URL`, `LLAMACPP_EXTRACTION_MODEL`, `EMBEDDING_PROVIDER`, `LLAMACPP_EMBEDDING_*` — **si impostano nel suo repo** |
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
(`REDIS_VECTOR_DIM`, 1024 per Qwen3-Embedding-0.6B — misurato sul gateway, non
assunto). Cambiare modello vuol dire ricostruire l'indice e re-ingestare; il
repo KG ha una guardia che rifiuta di scrivere su un indice di larghezza
diversa invece di corrompere i vettori.

Il sidecar **non è un servizio dei compose di Limen**: gira dal suo repo
(`docker-compose.ghcr.yml`, con neo4j + redis + kg-api + ui + mcp + agents), e
Limen si limita a puntargli `KG__BASE_URL`. L'entry che c'era prima nel compose
demo non era mai stata avviabile: immagine inesistente
(`knowledge-graph:latest` — quel repo pubblica `kg-api`, `kg-ui`, `kg-mcp`,
`kg-agents`), dipendenze `neo4j`/`redis` non definite, e `host.docker.internal`
senza `extra_hosts`.

> **Stato al 2026-09-03**: `kg-api:latest` su GHCR è ancora costruita da
> `eab6c0b` (11 giugno). La CI di quel repo è rossa per un `ruff` non pinnato e
> `docker-publish` è gated sulla CI, quindi il provider llama.cpp/OpenAI è su
> `main` ma **non nell'immagine**. Tracciato in knowledge-graph#7 (blocco) e
> #6 (provider `openai` di prima classe).
