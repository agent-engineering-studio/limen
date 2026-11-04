<p align="center">
  <img src="docs/images/banner.png" alt="Limen — Landslide Monitoring Framework" width="100%">
</p>

<h1 align="center">Limen</h1>

<p align="center">
  <b>Dove, in Italia, il terreno può franare, l'acqua salire o il bosco bruciare, adesso e nelle prossime 72 ore?</b><br>
  Una mappa aperta e spiegabile del pericolo di <b>frane, allagamenti e incendi</b>, un chilometro quadrato alla volta.
</p>

<p align="center">
  🗺️ <a href="https://limen.agentengineering.it/"><b>Apri la mappa</b></a> ·
  📖 <a href="#come-funziona">Come funziona</a> ·
  🚀 <a href="#avvio-rapido-sul-tuo-computer">Avvio rapido</a> ·
  🛰️ <a href="#i-dati-ogni-fonte-e-la-sua-licenza">Fonti dei dati</a> ·
  🧩 <a href="#le-librerie-collegate">Librerie</a> ·
  ☕ <a href="#sostieni-limen">Sostienici</a>
</p>

<p align="center">
  🇬🇧 <a href="./README.md">English</a> · 🇮🇹 <b>Italiano</b>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.12+-blue.svg" alt="Python 3.12+"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/licenza-EUPL--1.2-green.svg" alt="Licenza: EUPL-1.2"></a>
  <a href="https://github.com/astral-sh/uv"><img src="https://img.shields.io/badge/managed%20by-uv-261230" alt="uv"></a>
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/badge/lint-ruff-261230" alt="ruff"></a>
  <a href="http://mypy-lang.org/"><img src="https://img.shields.io/badge/typed-mypy%20--strict-blue" alt="mypy --strict"></a>
  <img src="https://img.shields.io/badge/dati-100%25%20aperti-orange" alt="Solo dati aperti">
  <img src="https://img.shields.io/badge/cloud-nessuno%20(self--hosted)-lightgrey" alt="Self-hosted, nessun cloud provider">
</p>

<p align="center">
  <a href="https://limen.agentengineering.it/"><img src="docs/images/screenshots/home.it.webp" alt="Home di Limen: «Il rischio del territorio, cella per cella» — 312.550 celle monitorate, 20 regioni, aggiornamento ogni ora, griglia di 1 km²" width="100%"></a>
</p>

---

## Indice

- [Limen in un minuto](#limen-in-un-minuto)
- [Cosa si vede sulla mappa](#cosa-si-vede-sulla-mappa)
- [Come funziona](#come-funziona)
- [Avvio rapido: sul tuo computer](#avvio-rapido-sul-tuo-computer)
- [Configurazione: il file `.env`, passo per passo](#configurazione-il-file-env-passo-per-passo)
- [I dati: ogni fonte e la sua licenza](#i-dati-ogni-fonte-e-la-sua-licenza)
- [Le librerie collegate](#le-librerie-collegate)
- [Architettura](#architettura)
- [Funziona? Cosa abbiamo misurato](#funziona-cosa-abbiamo-misurato)
- [Installazione su un server](#installazione-su-un-server)
- [Backup e ripristino](#backup-e-ripristino)
- [Test e quality gate](#test-e-quality-gate)
- [Stato e roadmap](#stato-e-roadmap)
- [Licenze e attribuzioni](#licenze-e-attribuzioni)
- [Sostieni Limen](#sostieni-limen) · [Contribuire](#contribuire-e-governance)

---

## Limen in un minuto

L'Italia ha più di **721.000 frane censite**, circa **6,8 milioni di persone**
che vivono dove i fiumi possono esondare, e ogni estate porta gli incendi.
L'allertamento ufficiale della Protezione Civile dà **un colore per zona**
(una zona sono decine di comuni), per oggi e domani.

**Limen** (in latino *soglia*) guarda più da vicino. Divide l'intero Paese in
**312.550 quadrati di 1 km²** e, **ogni ora**, fa a ciascuno tre domande:

| | Pericolo | La domanda, in parole semplici | Cosa fa salire il pericolo |
|---|---|---|---|
| 🟣 | **Frana** | *Questo versante è fragile, e sta ricevendo troppa pioggia?* | pendenza, frane già avvenute, terreni argillosi × pioggia oltre il livello che in passato ha innescato frane, più terremoti recenti e versanti bruciati |
| 🔵 | **Allagamento** | *L'acqua può arrivare qui, e sta arrivando?* | terreno che le carte di pericolosità già segnano come allagabile × pioggia forte (prevista **e** già caduta) o un fiume molto sopra la sua piena ordinaria |
| 🩷 | **Incendio** | *Un fuoco qui oggi attecchirebbe e si propagherebbe?* | l'indice meteorologico canadese di pericolo d'incendio (FWI: secco, vento, caldo) × il combustibile a terra e la pendenza |

Ogni risposta è un **punteggio da 0 a 1**, mostrato in **cinque classi**
(nessuna · bassa · moderata · alta · molto alta) su una mappa pubblica, con
una **previsione a 72 ore** e **avvisi** quando una cella supera una soglia.

Tre cose rendono Limen diverso:

1. **Ogni numero si può spiegare.** Il punteggio viene da una formula scritta,
   non da una scatola nera. Clicchi una cella e vedi quale ingrediente l'ha
   fatto salire: la pioggia, la pendenza, il fiume.
2. **L'AI scrive parole, mai numeri.** Un modello linguistico trasforma il
   risultato in una breve sintesi per regione. Non può cambiare un punteggio,
   e un test lo verifica.
3. **Aperto fino in fondo.** Solo dati aperti, codice aperto (EUPL-1.2), su un
   nostro server, nessun cloud provider, nessun login, nessun tracciamento.

> [!IMPORTANT]
> Limen è uno strumento di **supporto alle decisioni**. I suoi risultati sono
> indicatori modellati, **non allerte ufficiali della Protezione Civile**.
> Affianca il bollettino ufficiale: il bollettino dice *quale zona*; Limen
> prova a dire *dove dentro la zona, perché, e cosa succede dopo*.

**Non sei uno sviluppatore?** Le pagine divulgative in
[`docs/divulgazione/`](./docs/divulgazione/README.md) e la pagina
**Come funziona** del [sito](https://limen.agentengineering.it/#/come-funziona)
spiegano tutto senza gergo tecnico.

---

## Cosa si vede sulla mappa

<table>
<tr>
<td width="50%"><a href="https://limen.agentengineering.it/#/dashboard"><img src="docs/images/screenshots/dashboard-italy.it.webp" alt="Dashboard: tutta l'Italia colorata per pericolo stimato, con il numero di aree in classe alta per pericolo e la timeline a 72 ore"></a></td>
<td width="50%"><a href="https://limen.agentengineering.it/#/dashboard"><img src="docs/images/screenshots/dashboard-cells.it.webp" alt="Ingrandimento sulla Puglia: le singole celle da 1 km, con le celle di allagamento lungo i fiumi del Tavoliere in rosso e i confini dei comuni"></a></td>
</tr>
<tr>
<td><b>Tutto il Paese.</b> Scegli un pericolo (o tutti), guarda quante aree
sono in classe alta e trascina la timeline a <b>+24, +48, +72 ore</b>.</td>
<td><b>Ingrandisci e le regioni diventano celle.</b> Qui la piana di Foggia:
le fasce allagabili lungo i fiumi si accendono, cella per cella. Ogni cella
apre la scomposizione del suo punteggio.</td>
</tr>
<tr>
<td colspan="2"><a href="https://limen.agentengineering.it/#/regioni"><img src="docs/images/screenshots/regions-to-watch.it.webp" alt="Regioni da monitorare: regioni ordinate per pericolo stimato, l'allerta ufficiale su ogni riga e una breve sintesi scritta dall'AI per ogni pericolo"></a></td>
</tr>
<tr>
<td colspan="2"><b>Regioni da monitorare.</b> Le regioni ordinate dai numeri,
con accanto l'allerta ufficiale e una breve sintesi scritta da Claude per
ogni pericolo. La sintesi spiega; l'ordine e i colori vengono solo dalle
formule. Il rapporto si scarica in PDF.</td>
</tr>
</table>

Altre pagine del sito: **Verifiche** (`#/verifiche`, notizie di eventi reali
confrontate con quello che Limen aveva previsto prima), **Integrazioni**
(`#/integrazioni`, le API per altri software e agenti AI), **Sensori**
(`#/sensori`, una rete aperta di sensori sul territorio), **Fonti**
(`#/fonti`) e **Diagnostica ML** (`#/diagnostica-ml`).

---

## Come funziona

<p align="center">
  <img src="docs/images/how-it-works.it.svg" alt="Come funziona Limen: 1 legge i dati aperti (meteo, radar, fiumi, carte del suolo, satelliti, terremoti); 2 li porta su 312.550 celle da 1 km²; 3 calcola con tre formule leggibili per frana, allagamento e incendio, da 0 a 1 in cinque classi; 4 condivide su mappa pubblica, avvisi, sintesi AI e API aperte. Ritmo: ogni ora, 4 volte al giorno per la previsione a 72 ore, ogni 15–45 minuti su pioggia al radar o fuochi da satellite, ogni notte per i controlli ML e i backup." width="100%">
</p>

**1 · Legge.** Limen raccoglie dati pubblici: previsioni e archivio meteo, il
radar nazionale della pioggia, la portata dei fiumi, le carte delle frane e
delle aree allagabili, il terreno, l'uso del suolo, i fuochi visti dai
satelliti, i movimenti del suolo misurati dai satelliti radar, i terremoti.
[Tutte le fonti sono elencate più sotto](#i-dati-ogni-fonte-e-la-sua-licenza),
con le loro licenze.

**2 · Localizza.** Tutto viene portato sulla stessa griglia di celle da 1 km².
Quello che non cambia (pendenza, suolo, carte di pericolosità) si calcola una
volta per cella. Quello che cambia (pioggia, fiumi, meteo d'incendio) si legge
ogni ora su un reticolo di punti meteo, e ogni cella legge il punto più
vicino.

**3 · Calcola.** Una formula per pericolo, con ogni peso e ogni soglia in un
file YAML leggibile ([`src/limen/config/hazards/`](./src/limen/config/hazards/)):

```text
frana        = media pesata di  terreno (S) · pioggia vs soglia di Caine (M) · terremoti (E)
                                · incendi recenti (F) · acqua in fiumi e suolo (H) · moto del suolo (K)
allagamento  = suscettibilità × max( innesco pluviale , innesco fluviale )
incendio     = indice meteo d'incendio × ( base + combustibile + pendenza )
```

Due scelte di progetto proteggono da una falsa calma:

- **Il massimo, non la somma.** Per gli allagamenti pioggia e fiume sono due
  modi diversi per finire sott'acqua: Limen prende il più forte, così due
  segnali moderati non ne inventano uno grave.
- **«Non misurato» non vuol dire «nessun pericolo».** Se una fonte di dati è
  giù, le celle interessate si disegnano in **grigio**, come quelle non
  valutate, mai nel colore della calma. Uno zero che significa solo *non lo
  sappiamo* sarebbe l'unico errore che rassicura a torto.

**4 · Condivide.** Il risultato va sulla mappa, negli avvisi (Telegram,
e-mail, MQTT, webhook), nelle sintesi regionali scritte da un'AI che **non
cambia mai un numero**, e su API aperte (REST, MCP per gli agenti AI, A2A).

<details>
<summary><b>Il flusso passo per passo</b> (per sviluppatori)</summary>

Ogni esecuzione è una catena di piccoli passi («executor») di un Multi-Agent
Framework:

```mermaid
flowchart LR
    A[AreaResolver<br/>quali celle] --> B[StaticFactors<br/>pendenza, suolo, carte]
    B --> C[MeteoFetch<br/>pioggia, umidità del suolo]
    C --> D[SeismicCheck<br/>INGV]
    D --> E[FireCheck<br/>EFFIS, FIRMS]
    E --> F[SensorFetch<br/>IoT opzionale]
    F --> G[RiskScoring<br/>formula pura]
    G --> H[EscalationGate]
    H --> I[PersistResult<br/>PostGIS]
    I --> J[AlertDispatch<br/>dedup + canali]
```

L'allagamento aggiunge `FloodForecastFetch` (pioggia prevista + fiumi GloFAS)
e `ObservedRain` (il «Merging» radar-pluviometri del DPC); l'incendio aggiunge
`FwiUpdate` (la catena del Fire Weather Index, una per punto meteo). Il motore
di calcolo è una **funzione pura**: niente database, niente rete, niente AI.

</details>

---

## Avvio rapido: sul tuo computer

**Ti servono:** [Docker](https://docs.docker.com/get-docker/) con Compose,
[`uv`](https://docs.astral.sh/uv/getting-started/installation/) (installa lui
Python 3.12), `make` e Node 22 per il frontend della mappa. Circa 10 GB di
disco libero per una demo regionale; nessuna chiave API.

```bash
git clone https://github.com/agent-engineering-studio/limen.git
cd limen
cp .env.example .env               # va bene così per una demo locale
uv sync --all-groups               # installa le dipendenze Python
make up                            # avvia Postgres + PostGIS, GeoServer, tile server, frontend
make init                          # costruisce i dati (vedi sotto) — si può rilanciare
uv run limen serve                 # API su http://localhost:8080/docs
( cd frontend && npm ci && npm run dev )   # mappa su http://localhost:5173
```

Cosa fa `make init`, in ordine (ogni passo è idempotente: puoi fermarlo e
riprenderlo):

```mermaid
flowchart LR
    M[migrate<br/>crea le tabelle] --> S[seed<br/>20 regioni,<br/>griglia 1 km²]
    S --> I[ingest-events<br/>catalogo frane<br/>e-ITALICA]
    I --> D[dati statici<br/>scarica ISPRA, ISTAT,<br/>CORINE, geologia, DTM]
    D --> B[fattori per cella<br/>pendenza, frane, carte<br/>di pericolosità, combustibile]
    B --> C[calibrate<br/>normalizzazione<br/>per regione]
```

Il passo dei dati statici (`scripts/load_static_data.sh`, lo stesso percorso
per `make up`, `make init` e `make static-data`) **scarica da solo** tutto
quello che non richiede un account: l'inventario frane IFFI e i mosaici di
pericolosità PAI da IdroGEO (`limen geodati-sync`, tramite
[ispra-idrogeo](#ispra-idrogeo)), i confini ISTAT, CORINE 2018, la carta
geolitologica 1:500k e il DTM a 5 m (HR-DTM IRPI-CNR, Zenodo). Li carica nel
PostGIS di [mcp-geo-server](#mcp-geo-server), aggiunge le aree bruciate EFFIS
e, con la chiave, i movimenti del suolo EGMS, poi calcola i fattori per cella.
Il primo giro completo per l'Italia pesa ~25 GB (DTM compreso); i successivi
saltano quello che non è cambiato.

Un altro dato ISPRA arriva invece di notte: l'**esposizione per comune**. Il
passo notturno `esposizione_ispra` salva in `esposizione_comuni` quanti
residenti di ogni comune vivono nelle aree a pericolosità frana P3+P4 del PAI
e idraulica P2 (censimento ISTAT 2021), più edifici e imprese, dall'API di
IdroGEO. Le risposte stanno in `LIMEN_DATA_DIR/idrogeo` e si richiedono solo
dopo 30 giorni: quasi tutte le notti si leggono dal disco in ~2 s.
`/api/comuni` le restituisce come `esposizione_ispra`; non entrano in nessun
punteggio. `limen esposizione-sync` riempie la tabella subito.

Poi lancia un calcolo e guarda la mappa:

```bash
LIMEN_MONITOR_AOI=it-puglia uv run limen monitor-once   # calcola una regione adesso
uv run limen data-status                                # quali strati di dati sono caricati
uv run limen report build                               # report HTML statico → site/index.html
```

> [!TIP]
> Seminare tutte e venti le regioni crea ~312.000 celle e richiede tempo. Per
> un primo sguardo segui [`docs/demo.md`](./docs/demo.md), che gira su
> un'area piccola in pochi minuti.

**Su Neon (Postgres serverless, solo dev/test):** imposta
`DB__CONNECTION_STRING=...?sslmode=require` e
`SCHEDULER__CACHE_CLEANUP=apscheduler`; nient'altro cambia.

---

## Configurazione: il file `.env`, passo per passo

Tutto si configura con variabili d'ambiente, di solito in un file `.env` nella
radice del repository. [`.env.example`](./.env.example) elenca ogni variabile
con i commenti: copialo e cambia solo quello che ti serve.

**Una regola per leggerlo:** il doppio trattino basso vuol dire «sezione →
campo». `FIRMS__MAP_KEY` è il campo `map_key` della sezione `firms`; le
impostazioni sono tipizzate e validate all'avvio da
[`limen.config.settings`](./src/limen/config/settings.py).

Limen è fatto per **partire senza nessuna chiave** e arricchirsi man mano che
le aggiungi. Ogni sorgente esterna è *fail-closed*: senza la sua chiave quel
flusso resta spento (e lo dice nei log), il resto continua a funzionare.

```mermaid
flowchart LR
    L0["<b>Livello 0 · nessuna chiave</b><br/>meteo Open-Meteo pubblico, radar DPC,<br/>terremoti INGV, aree bruciate EFFIS,<br/>archivio FIRMS, alluvioni Copernicus EMS,<br/>frane e-ITALICA"]
    L1["<b>Livello 1 · strati statici</b><br/>GEOSERVER_SOURCE__DB_DSN → ISPRA, ISTAT,<br/>CORINE, geologia, DTM scaricati all'init<br/>impermeabilizzazione, OSM: make fetch-static"]
    L2["<b>Livello 2 · chiavi gratuite</b><br/>FIRMS__MAP_KEY → fuochi da satellite in diretta<br/>COPERNICUS__EWDS_KEY → fiumi GloFAS<br/>EGMS__SERVICE_KEY → moto del suolo"]
    L3["<b>Livello 3 · produzione</b><br/>OPENMETEO__FORECAST_URL → server meteo proprio<br/>gateway LLM + ANTHROPIC_API_KEY → sintesi<br/>NOTIFICATIONS__* → avvisi · BACKUP__* → backup"]
    L0 --> L1 --> L2 --> L3
```

### Le chiavi che sbloccano altri dati

Sono tutte **gratuite**. Nessuna serve per partire.

| Variabile | Cosa accende | Dove si ottiene | Senza |
|---|---|---|---|
| `GEOSERVER_SOURCE__DB_DSN` | lo scarico dei dati di base all'init e i fattori per cella che ne derivano: IFFI, carte PAI di frana e allagamento, confini ISTAT, CORINE, geologia, DTM, tenuti nel PostGIS di [mcp-geo-server](#mcp-geo-server) | lo stack GeoServer, avviato da `make init` | termine del terreno più povero per le frane; mappa allagamenti uniforme |
| `LIMEN_DEM_RASTER` | usare un proprio modello del terreno (es. TINITALY 10 m) al posto dell'HR-DTM 5 m scaricato all'init | un GeoTIFF su disco ([`data/README.md`](./data/README.md)) | si usa l'HR-DTM scaricato |
| `FIRMS__MAP_KEY` | i fuochi NASA da satellite in tempo quasi reale ogni 45 min; un incendio può far partire un calcolo entro poche ore | [firms.modaps.eosdis.nasa.gov/api/map_key](https://firms.modaps.eosdis.nasa.gov/api/map_key/) | solo l'archivio annuale (senza chiave) |
| `COPERNICUS__EWDS_KEY` | la previsione di portata dei fiumi e la *piena ordinaria* di ciascun fiume da Copernicus GloFAS | account ECMWF su [ewds.climate.copernicus.eu](https://ewds.climate.copernicus.eu/how-to-api); accettare una volta la licenza CEMS-Floods | GloFAS tramite l'API pubblica di Open-Meteo |
| `EGMS__SERVICE_KEY` (o `__SERVICE_KEY_FILE`) | le velocità del suolo da Sentinel-1 (EGMS), per le feature del modello ML | [land.copernicus.eu](https://land.copernicus.eu) → profilo → *API Tokens* (il JSON si vede una volta sola) | nessuna feature di moto del suolo |
| `OPENMETEO__FORECAST_URL` / `__ARCHIVE_URL` | un proprio server Open-Meteo (`make meteo-up`); le 10.000 chiamate al giorno dell'API pubblica non bastano per tutta l'Italia | self-hosted, profilo compose `meteo` | API pubblica (va bene per una regione) |
| `ANTHROPIC_API_KEY` | le sintesi regionali con Claude, sotto un tetto mensile (`LLM__ANTHROPIC_BUDGET_MENSILE_USD`, 10 $ di default) | [console.anthropic.com](https://console.anthropic.com) | modello locale via llama.cpp, o un testo deterministico |
| `NOTIFICATIONS__*` | avvisi su Telegram, e-mail, MQTT o webhook (`NOTIFICATIONS__ENABLED_CHANNELS`) | il tuo bot / SMTP / broker | gli avvisi restano nel database e sulla mappa |
| `MCP_ADMIN_TOKEN` | gli strumenti di amministrazione del server MCP (lanciare un giro, costruire un report) | una stringa casuale lunga | strumenti admin disattivati |

### Le variabili che toccherai più spesso

| Variabile | Default | Cosa fa |
|---|---|---|
| `LIMEN_DATA_ROOT` | la cartella `data/` del repo | **Una sola cartella per tutti i dati** del deployment: dataset, report, modelli, dati di GeoServer, OSM, radar. Spostare Limen = copiare questa cartella e cambiare questa riga. Se impostata, deve essere assoluta. |
| `DB__CONNECTION_STRING` | `postgresql://limen:limen@localhost:5432/limen` | PostgreSQL 16 + PostGIS. Aggiungi `?sslmode=require` per Neon. |
| `OBJECT_STORE__BACKEND` | `filesystem` | `filesystem` o `s3` (qualsiasi store S3-compatibile: MinIO, R2, B2, via `OBJECT_STORE__ENDPOINT_URL`). |
| `SCHEDULER__ENABLED` | `true` | I job periodici girano nel processo `limen worker`; `false` nel container dell'API. |
| `SCHEDULER__FORECAST_CELLS_HOURS_UTC` | `[2, 8, 14, 20]` | Quando si ricalcola la previsione a 72 ore per cella. |
| `LLM__PROVIDER` | _vuoto_ | Forza `anthropic` / `openai` / `foundry` / `ollama` / `llamacpp`. Vuoto: vince una chiave cloud, altrimenti llama.cpp. |
| `LLM__LLAMACPP_BASE_URL` | `http://127.0.0.1:8091` | Il gateway d'inferenza LiteLLM (non `:8081`, che è GeoServer). Da un container: `host.docker.internal`. |
| `SCORING__MODE` | `champion_only` | `shadow` fa girare anche lo sfidante ML di notte, scrivendo solo in `model_runs`. |
| `FORECAST__ENABLED` | `true` | Giro previsionale e avvisi «PREVISIONE». |
| `NOWCAST__*` | attivo | Innesco dal radar DPC: pioggia intensa vista dal radar fa partire subito un calcolo. |
| `LOG_LEVEL` / `LOG_JSON` | `INFO` / `false` | Log strutturati. |

<details>
<summary><b>Altre variabili</b> (report, ruoli LLM, porte, immagini)</summary>

| Variabile | Default | Note |
|-----------|---------|------|
| `SCHEDULER__CACHE_CLEANUP` | `apscheduler` | `pg_cron` o `apscheduler`. **Su Neon usa APScheduler.** |
| `EGMS__CARTELLA` | `data/egms` | Tile EGMS, conservate fra una sincronizzazione e l'altra (in Docker: il volume `LIMEN_EGMS_DIR` su `/var/lib/limen/egms`). |
| `LLM__MODELS__<RUOLO>` | id Claude | Mappa ruolo → modello. `LLM__MODELS__FEDELTA` è un id Claude inviato come Message Batch. Vedi [`docs/inference.md`](./docs/inference.md). |
| `LLM__LLAMACPP_TIMEOUT_SECONDS` | `120` | Tetto per i ruoli senza override; `LLM__LLAMACPP_ROLE_TIMEOUT_SECONDS` (JSON) per ruolo. |
| `LLM__OLLAMA_BASE_URL` / `LLM__OLLAMA_MODEL` | `http://localhost:11434` / `qwen3.6:latest` | Host e modello Ollama (serve `LLM__PROVIDER=ollama`). |
| `REPORT__HTML_ENABLED` | `true` | Report HTML statico; `__HTML_INTERVAL_HOURS` (1), `__HTML_MIN_LEVEL` (High), `__HTML_PUBLISH` (false). |
| `NOTIFICATIONS__WEBHOOK__URL` / `__TOKEN` | _vuoto_ | Gateway per agenti (es. OpenClaw `/hooks`) e bearer token. |
| `LIMEN_ITALICA_CSV` | _vuoto_ | CSV e-ITALICA locale; se manca, si scarica da Zenodo. |
| `LIMEN_IMAGE_PREFIX` / `LIMEN_IMAGE_TAG` | _vuoto_ | Scarica le immagini da GHCR invece di costruirle ([più sotto](#immagini-costruite-qui-o-scaricate-da-ghcr)). |
| `LIMEN_DOMINIO` | _vuoto_ | Il tuo dominio: `make up` aggiunge Caddy con i certificati Let's Encrypt. |
| `BACKUP__*` | _vuoto_ | Bucket S3-compatibile per il backup notturno ([più sotto](#backup-e-ripristino)). |
| `LIMEN_*_BIND` | `127.0.0.1` | Indirizzo di ogni porta pubblicata ([più sotto](#porte-pubblicate-docker-scavalca-ufw)). |

L'elenco completo, con i commenti, è in [`.env.example`](./.env.example).

</details>

---

## I dati: ogni fonte e la sua licenza

Limen usa **solo dati aperti**. Ecco cosa legge, per cosa, e a quali
condizioni.

| Fonte | 🟣 Frana | 🔵 Allagamento | 🩷 Incendio |
|---|:---:|:---:|:---:|
| **Meteo e acqua** | | | |
| Open-Meteo (previsione + archivio) | ● pioggia, umidità del suolo | ● pioggia | ● caldo, umidità, vento, pioggia |
| Radar pioggia DPC | ○ innesco | ● pioggia già caduta | |
| Copernicus GloFAS | ○ termine fluviale | ● portata dei fiumi | |
| **Suolo** | | | |
| ISPRA IFFI + PAI | ● frane storiche, pericolosità | ● carta di pericolosità idraulica | |
| Modello del terreno (DTM) | ● pendenza | | ● pendenza |
| CORINE · geologia · impermeabilizzazione · OSM | ● tipo di roccia | ● suolo sigillato | ● combustibile, case vicine |
| Copernicus EGMS | ○ moto del suolo (ML) | | |
| **Eventi** | | | |
| Terremoti INGV | ● terremoti recenti | | |
| Fuochi NASA FIRMS | ● versanti bruciati | | ● storico incendi, innesco |
| Aree bruciate EFFIS | | | ✓ verità a terra |
| Aree allagate Copernicus EMS | | ✓ verità a terra | |
| Frane datate e-ITALICA | ✓ verità a terra | | |

● entra nel punteggio · ○ ingresso secondario o opzionale · ✓ verità a
terra: eventi passati usati per tarare e verificare le formule, non per
calcolare il punteggio di oggi.

| Fonte | Cosa prende Limen | Per cosa | Licenza | Chiave? |
|---|---|---|---|---|
| [**Open-Meteo**](https://open-meteo.com) (ECMWF IFS, ICON-EU, ERA5, ERA5-Land) | pioggia oraria, umidità del suolo, temperatura, umidità, vento; previsione e archivio | tutti e tre i pericoli | CC-BY 4.0 (dati: Copernicus / DWD / ECMWF) | no |
| [**Piattaforma radar DPC**](https://radar.protezionecivile.it) | SRI nazionale (1 km, 5 min) e cumulate «Merging» radar + pluviometri | innesco nowcast; pioggia già caduta per gli allagamenti | CC-BY-SA 4.0 | no |
| [**Copernicus EMS — GloFAS**](https://ewds.climate.copernicus.eu) | previsione di portata per nodo; piena ordinaria di ogni nodo dallo storico pluriennale | allagamento (ramo fluviale) | licenza CEMS-Floods, attribuzione obbligatoria | chiave EWDS gratuita (o via Open-Meteo) |
| [**ISPRA IdroGEO**](https://idrogeo.isprambiente.it) | inventario frane IFFI (721.365 frane), mosaici PAI di pericolosità da frana e idraulica | terreno per le frane; suscettibilità agli allagamenti | CC-BY 4.0 | no |
| **HR-DTM 5 m** (IRPI-CNR, Zenodo) o **TINITALY 10 m** (INGV) | quota → pendenza, esposizione, curvatura | frana, incendio | CC-BY 4.0 | no |
| [**CORINE Land Cover 2018**](https://groupware.sinanet.isprambiente.it) (SINAnet/ISPRA) | uso del suolo → tipo di combustibile | incendio | CC-BY | no |
| **Carta geolitologica d'Italia 1:500k** (PCN/MASE) | tipo di roccia e di terreno | frana | CC-BY 4.0 | no |
| [**Copernicus Land — impermeabilizzazione**](https://land.copernicus.eu) | suolo sigillato (%) | allagamento (deflusso urbano) | licenza aperta Copernicus Land | no |
| [**OpenStreetMap**](https://www.openstreetmap.org) | strade, ferrovie; mappa di base | esposizione; mappa | ODbL | no |
| [**Copernicus Land — EGMS**](https://egms.land.copernicus.eu) | velocità del suolo da InSAR Sentinel-1 (Ortho L3, 100 m) | feature ML (non ancora la mappa) | licenza aperta Copernicus Land | chiave di servizio CLMS gratuita |
| [**INGV**](https://terremoti.ingv.it) | terremoti (FDSN), ShakeMap | frana (termine sismico) | CC-BY 4.0 | no |
| [**NASA FIRMS**](https://firms.modaps.eosdis.nasa.gov) | fuochi attivi (VIIRS 375 m, MODIS 1 km), archivio dal 2000 | storico incendi; termine post-incendio delle frane; innesco | dati aperti NASA, con citazione | MAP_KEY gratuita (solo tempo reale) |
| [**EFFIS**](https://effis.jrc.ec.europa.eu) | perimetri delle aree bruciate; FWI ufficiale | verità a terra e confronto per gli incendi | condizioni Copernicus EFFIS | no |
| [**Copernicus EMS Rapid Mapping**](https://rapidmapping.emergency.copernicus.eu) | aree allagate osservate + dove il satellite ha guardato | verità a terra per gli allagamenti | © UE, libero con attribuzione | no |
| [**e-ITALICA**](https://doi.org/10.5281/zenodo.14204473) (CNR-IRPI) | frane datate innescate da pioggia, in tutta Italia | taratura e backtest delle frane | CC-BY 4.0 | no |
| **ISTAT** | confini comunali, provinciali, regionali (2023) | griglia, classifiche per comune | CC-BY | no |

Dove ogni fonte si configura, si aggiorna e si salva su disco è in
[`data/README.md`](./data/README.md); la guida
[`docs/divulgazione/04-fonti-dati-open.md`](./docs/divulgazione/04-fonti-dati-open.md)
racconta la stessa storia per un pubblico generale.

---

## Le librerie collegate

Una parte del lavoro più difficile di Limen è stata **parlare con le fonti di
dati**: formati non documentati, servizi che rispondono zero invece di un
errore, un'acciaieria che dal satellite sembra un incendio. Quel lavoro l'abbiamo
estratto in **piccole librerie Python open source, tipizzate**, che chiunque
può usare, con o senza Limen.

```mermaid
flowchart TB
    subgraph PyPI["Su PyPI · Apache-2.0"]
        CEMS["copernicus-ems<br/>aree allagate"]
        EG["egms-client<br/>moto del suolo"]
        FC["firms-client<br/>fuochi attivi"]
        ID["ispra-idrogeo<br/>frane e carte di pericolosità<br/>+ idrogeo-mcp"]
        FWI["fwi-chain<br/>Fire Weather Index"]
        EF["effis-client<br/>aree bruciate, FWI ufficiale"]
        RT["rainfall-thresholds<br/>la pioggia che innesca frane"]
        IS["imageserver-export<br/>suolo sigillato e copertura del suolo"]
    end
    MGS["mcp-geo-server · MIT<br/>GeoServer + PostGIS + agente MCP"]
    L["<b>Limen</b>"]
    CEMS --> L
    EG --> L
    FC --> L
    FWI --> L
    EF --> L
    RT --> L
    ID --> L
    IS --> L
    MGS -- "strati ISPRA in PostGIS<br/>sovrapposizioni WMS" --> L
```

Limen le fissa con `~=`, così una versione minore richiede un aggiornamento
deliberato, e ne usa solo le parti **pure** (costruzione delle richieste,
parsing, validazione): le chiamate di rete passano dal client condiviso e
dalla politica di retry di Limen (`limen.integrations._http`), e la regola del
«risultato neutro in caso di errore» resta in Limen. I numeri che tarano un
pericolo restano in `src/limen/config/hazards/*.yaml`, mai nelle costanti di
una libreria.

| Pacchetto | Versione in Limen | Licenza |
|---|---|---|
| [`copernicus-ems`](https://pypi.org/project/copernicus-ems/) | `~=0.4.0` | Apache-2.0 |
| [`egms-client`](https://pypi.org/project/egms-client/) | `~=0.7.0` | Apache-2.0 |
| [`firms-client`](https://pypi.org/project/firms-client/) | `~=0.4.0` | Apache-2.0 |
| [`ispra-idrogeo`](https://pypi.org/project/ispra-idrogeo/) | `~=0.7.0` | Apache-2.0 |
| [`fwi-chain`](https://pypi.org/project/fwi-chain/) | `~=1.0.0` | Apache-2.0 |
| [`effis-client`](https://pypi.org/project/effis-client/) | `~=0.1.2` | Apache-2.0 |
| [`rainfall-thresholds`](https://pypi.org/project/rainfall-thresholds/) | `~=0.1.0` | Apache-2.0 |
| [`imageserver-export`](https://pypi.org/project/imageserver-export/) | `~=0.2.0` | Apache-2.0 |
| [`mcp-geo-server`](https://github.com/agent-engineering-studio/mcp-geo-server) | immagine Docker, commit fissato | MIT |

### copernicus-ems

[![PyPI](https://img.shields.io/pypi/v/copernicus-ems)](https://pypi.org/project/copernicus-ems/) ·
[GitHub](https://github.com/agent-engineering-studio/copernicus-ems) · Apache-2.0

**Cosa fa.** Legge [Copernicus EMS Rapid Mapping](https://rapidmapping.emergency.copernicus.eu/),
il servizio che mappa i disastri da immagini satellitari entro poche ore.
Elenca le attivazioni (es. `EMSR664`, Emilia-Romagna, maggio 2023) e i loro
prodotti, e scarica in GeoJSON gli **strati dell'evento osservato** (dove
l'acqua c'era davvero) e le **maschere di osservazione** (dove il satellite ha
davvero guardato). Nessun account, nessuna chiave; una sola dipendenza,
`httpx`.

**Come la usa Limen.** Costruisce la **verità a terra degli allagamenti**: 14
attivazioni italiane, 15.865 poligoni allagati, 3.593 celle in 9 regioni. La
maschera conta: dentro, *nessun poligono* vuol dire *osservato asciutto*;
fuori, un avviso è *non verificabile*, non falso. Comando: `make flood-events`
(`limen ingest-events --hazard flood`), poi `limen backtest-flood`. Codice:
[`integrations/copernicus_ems/`](./src/limen/integrations/copernicus_ems/).

### egms-client

[![PyPI](https://img.shields.io/pypi/v/egms-client)](https://pypi.org/project/egms-client/) ·
[GitHub](https://github.com/agent-engineering-studio/egms-client) ·
[Documentazione](https://agentengineering.it/egms-client/) · Apache-2.0

**Cosa fa.** Scarica l'archivio di [EGMS](https://egms.land.copernicus.eu/),
lo European Ground Motion Service: di quanti **millimetri all'anno** si muove
il suolo, misurato dai satelliti radar Sentinel-1. Gestisce l'accesso con la
chiave di servizio CLMS, la ricerca, lo scarico e la cache dei prodotti L2A,
L2B e Ortho L3, i mosaici e le serie storiche in GeoParquet.

**Come la usa Limen.** `limen sync-egms` (lanciato da `make init` quando la
chiave c'è) scarica le tile Ortho L3 dell'Italia, verticale ed est-ovest a
100 m: ~25 minuti e 164 tile (~420 MB) la prima volta, niente le successive.
Limen usa la ricerca e il parsing della libreria e scarica le tile da sé
(`integrations/egms/clms.py`), poi calcola per ogni cella il 90° percentile
della velocità e il numero di pixel validi (`cell_insar_features`). Un passo
notturno controlla se è uscita una nuova release. Serve `EGMS__SERVICE_KEY`;
oggi alimenta le feature ML, non la mappa. Codice:
[`integrations/egms/`](./src/limen/integrations/egms/).

### firms-client

[![PyPI](https://img.shields.io/pypi/v/firms-client)](https://pypi.org/project/firms-client/) ·
[GitHub](https://github.com/agent-engineering-studio/firms-client) · Apache-2.0

**Cosa fa.** Legge [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/): ogni
fuoco attivo visto dallo spazio dal 2000. Scarica gli **archivi annuali per
Paese** (aperti, senza chiave), interroga l'**API per area in tempo quasi
reale** (con una `MAP_KEY` gratuita) e classifica i rilevamenti, così da
**distinguere un incendio di vegetazione da un'acciaieria o da un vulcano**.

**Come la usa Limen.** In due modi:
- **Storico** (`make fire-history`): 391.987 rilevamenti italiani → 224.156
  eventi cella-giorno e una `fire_density` per cella, usata dalle feature ML
  degli incendi e per pesare quanto un incendio passato ha colpito un
  versante. Senza il filtro sul tipo, il luogo «più bruciato» d'Italia era
  l'acciaieria ex ILVA di Taranto.
- **Innesco in diretta** (`FIRMS__MAP_KEY`): ogni 45 minuti, nuovi fuochi in
  una regione fanno partire subito un calcolo, e il termine post-incendio
  delle frane si accende in poche ore invece di aspettare la carta delle aree
  bruciate.

Codice: [`integrations/firms/`](./src/limen/integrations/firms/).

### ispra-idrogeo

[![PyPI](https://img.shields.io/pypi/v/ispra-idrogeo)](https://pypi.org/project/ispra-idrogeo/) ·
[GitHub](https://github.com/agent-engineering-studio/ispra-idrogeo) · Apache-2.0

**Cosa fa.** Scarica da [IdroGEO](https://idrogeo.isprambiente.it/), la
piattaforma dove l'ISPRA pubblica quello che l'Italia sa di frane e
alluvioni: l'**inventario frane IFFI** (721.365 frane), i **mosaici nazionali
di pericolosità PAI**, gli eventi datati e l'API REST con gli indicatori di
rischio di qualsiasi regione, provincia o comune. I file restano in cache e si
aggiornano con richieste condizionali, così un aggiornamento notturno costa
poche centinaia di byte quando nulla è cambiato.

Dalla 0.5 è anche:

| | Novità | In parole semplici |
|---|---|---|
| 🤖 | **`idrogeo-mcp`, un server MCP** | `pip install "ispra-idrogeo[mcp]"`, lo aggiungi a Claude Desktop o a un altro agente e chiedi *«quante persone vivono in aree a pericolosità da frana elevata a Sarno, e qualcuno monitora quelle frane?»*. Dodici strumenti dalla 0.6: `find_area`, `area_risk`, `area_landslides`, `landslide`, `search_landslides`, `search_events`, `monitoring_sites`, `webcams`, `hazard_at` (la classe di pericolosità in un punto), `landslides_near` (le frane intorno a un punto), `code_list`, `download_dataset`. Tutti in sola lettura tranne lo scarico; le risposte si fermano a `limit` righe, così un agente non riceve mai 700.000 frane in una volta. |
| ⌨️ | **Il comando `idrogeo`** | `idrogeo fetch frane_piff --area molise`, `idrogeo summary pir comuni 72006`, `idrogeo landslides --since …`: gli scarichi stampano la cartella, tutto il resto JSON Lines, pronto per `jq` o per un caricamento in database. |
| 🗺️ | **GeoDataFrame e GeoParquet** | L'extra `[geo]` trasforma le righe dell'API e gli strati scaricati in tabelle GeoPandas. |
| 🔎 | **Filtri di ricerca tipizzati** | Frane per tipo di movimento e attività, eventi per area e data, siti di monitoraggio per stato, senza scrivere la sintassi PostgREST. |
| 🏷️ | **Codici decodificati** | Le 73 liste di codici dell'API, in quattro lingue: `strumentazione = [15, 22, 25]` diventa inclinometro, monitoraggio topografico, interferometria SAR. |
| 🔁 | **Solo quello che è cambiato** | `modified_since` per aggiornare in modo incrementale frane, eventi e siti di monitoraggio. |
| 📡 | **Siti di monitoraggio e webcam** | Chi sorveglia una frana, e con quali strumenti. |

```json
{ "mcpServers": { "idrogeo": { "command": "idrogeo-mcp" } } }
```

In questo repository `.mcp.json` lo collega già a Claude Code, tramite `uvx`
in un ambiente suo: il server MCP vuole `mcp>=2.0`, mentre il server MCP di
Limen gira su `fastmcp` e `mcp` 1.x, quindi i due non si installano mai
insieme.

**Come la usa Limen.** `limen geodati-sync`, passo 3 dei dati statici di
`make init`, scarica con lei l'inventario IFFI di ogni regione (più Bolzano e
Trento) e i mosaici nazionali PAI di frana e alluvione in
`GEOSERVER_SHAPEFILE_DIR`, da caricare nel PostGIS di mcp-geo-server. Limen
ne usa direttamente il client, perché i file (fino a 1,2 GB) vanno scritti
su disco in streaming: con `retries=0`, dentro la
politica di retry di Limen. L'ISPRA rigenera i file IFFI ogni notte, quindi un
file si richiede solo dopo `GEODATI__RIVALIDA_DOPO_GIORNI` (30 giorni).
Codice: [`integrations/idrogeo/`](./src/limen/integrations/idrogeo/).

### mcp-geo-server

[GitHub](https://github.com/agent-engineering-studio/mcp-geo-server) · MIT

**Cosa fa.** Uno stack GIS pronto in Docker: **PostGIS + GeoServer**, più un
bootstrap che carica gli shapefile di una cartella e li pubblica come strati
OGC WMS/WFS con stili tematici, e un **server MCP** in cui un agente AI guida
GeoServer in linguaggio naturale («quante frane nelle Marche?»), con
un'interfaccia web chat + mappa.

**Come lo usa Limen.** È la casa dei **grandi strati statici**: IFFI e PAI
dell'ISPRA, il mosaico idraulico, i confini ISTAT, il terreno, l'uso del suolo
e la geologia. `make init` lo avvia e carica tutto da sé; a mano:

```bash
make geoserver-up       # GeoServer :8081, web UI :8000, agente MCP :9000, PostGIS :55433
uv run limen geodati-sync   # scarica i dati di base in $LIMEN_DATA_ROOT/geoserver
make geoserver-init     # carica gli shapefile in PostGIS (GEO_INIT_FORCE=true per ricaricare)
make geoserver-sync     # copia IFFI + PAI nel database di Limen
```

Con `GEOSERVER_SOURCE__DB_DSN` impostata, `limen bootstrap-static` legge
questi strati e calcola i fattori per cella, e `limen seed-comuni` importa i
confini comunali. La mappa mostra gli strati PAI/IFFI in sovrapposizione
tramite il WMS di GeoServer (`/geoserver/ispra/wms`). Nulla nel calcolo orario
aspetta GeoServer. File compose:
[`infra/docker/docker-compose.geoserver.yml`](./infra/docker/docker-compose.geoserver.yml).

### Altre librerie estratte da Limen

| Libreria | Cosa fa | In Limen serve per |
|---|---|---|
| [`fwi-chain`](https://pypi.org/project/fwi-chain/) | Il Fire Weather Index canadese (Van Wagner 1987), puro e verificato sul giorno di riferimento pubblicato fino a 1e-9 | il motore degli incendi, una catena per punto meteo |
| [`effis-client`](https://pypi.org/project/effis-client/) | I perimetri delle aree bruciate EFFIS e le carte ufficiali del FWI (un MapServer pieno di sorprese) | la verità a terra degli incendi; `limen fwi-confronto` |
| [`rainfall-thresholds`](https://pypi.org/project/rainfall-thresholds/) | Eventi di pioggia e soglie intensità–durata (Caine) | il termine pioggia delle frane |
| [`imageserver-export`](https://pypi.org/project/imageserver-export/) ([sito](https://agentengineering.it/imageserver-export/)) | Un'area di qualunque ImageServer ArcGIS come un solo GeoTIFF: pixel allineati, valori «nessun dato» intatti, errori mandati con «200 OK» intercettati, file scritto solo quando è completo, con la provenienza nei tag del GeoTIFF; un download interrotto riparte dalle tessere già arrivate. Con `[mcp]` anche un server MCP, `imageserver-mcp` (valore in un punto, sintesi di un riquadro, export), in cui ogni numero lo calcola la libreria e non il modello. Prima applicazione: gli strati aperti di Copernicus Land che l'EEA pubblica senza account | il raster del suolo sigillato (`limen imperviousness-fetch`), che amplifica l'innesco pluviale delle alluvioni; `.mcp.json` collega `imageserver-mcp` a Claude Code tramite `uvx`, come `idrogeo-mcp` |

---

## Architettura

```mermaid
flowchart LR
    SRC["Fonti di dati aperte<br/>(vedi sopra)"] -->|httpx + retry| WK
    GS["mcp-geo-server<br/>GeoServer + PostGIS<br/>strati ISPRA"] -->|bootstrap| DB
    subgraph WK["limen worker · APScheduler"]
        H["giro orario<br/>calcolo · salvataggio · avvisi"]
        FC["previsione 72 h<br/>4 volte al giorno"]
        NT["notte<br/>ML shadow · drift · backup"]
        BR["sintesi<br/>regionali"]
    end
    WK --> DB[("PostgreSQL 16<br/>+ PostGIS")]
    BR <--> LLM["gateway LiteLLM<br/>llama.cpp · Claude"]
    WK --> N["Telegram · e-mail<br/>MQTT · webhook"]
    DB --> API["FastAPI<br/>REST + A2A"]
    DB --> T["pg_tileserv<br/>tile vettoriali"]
    DB --> MCP["MCP limen-ops<br/>per agenti AI"]
    API --> SPA["React + MapLibre<br/>mappa pubblica"]
    T --> SPA
    GS -->|sovrapposizioni WMS| SPA
```

**In breve:** un processo **worker** scarica i dati e calcola i punteggi a
orari fissi; tutto finisce in **PostgreSQL + PostGIS**; l'**API**, il **tile
server** e il **server MCP** leggono da lì; la **mappa** è un'app React
statica. L'AI sta di lato, a scrivere le sintesi.

| Strato | Tecnologia | Perché |
|---|---|---|
| Linguaggio | Python 3.12, [`uv`](https://github.com/astral-sh/uv), `mypy --strict` | tipizzato da capo a fondo, un solo lockfile |
| Database | PostgreSQL 16 + PostGIS, `asyncpg`, migrazioni in SQL puro, **niente ORM** | lo stesso codice su Docker, Neon o qualsiasi Postgres |
| Pianificazione | APScheduler in `limen worker` (`pg_cron` opzionale) | funziona dove `pg_cron` non c'è (Neon) |
| API | FastAPI: `/api/...`, `/docs`, `/redoc`, `/health`, A2A su `/a2a` | OpenAPI gratis |
| Mappa | Vite + React + Mantine + MapLibre GL, tile vettoriali pg_tileserv | niente server Node, tile veloci |
| AI | gateway LiteLLM → llama.cpp (locale) o Claude; MCP + A2A per gli agenti | prima il locale, cloud opzionale, spesa con tetto |
| Storage | `filesystem` o qualsiasi store S3-compatibile (MinIO, R2, B2) | nessun vincolo a un SDK cloud |
| Deploy | Docker Compose su un server proprio | niente AWS, Azure, GCP |

<details>
<summary><b>Ogni componente nel dettaglio</b></summary>

| Componente | Cosa fa | Cadenza | Implementazione |
|---|---|---|---|
| **Open-Meteo** | precipitazione oraria, umidità del suolo 0–7 / 7–28 cm, neve (previsione); precipitazione cumulata (archivio). Servito da **un'istanza nostra** (profilo compose `meteo`): le 10.000 chiamate al giorno dell'API pubblica si esaurivano e lasciavano allagamenti e incendi a zero su tutta l'Italia (#142) | in diretta, cache 30 min | `integrations/openmeteo/` + `CachedOpenMeteoClient` |
| **ISPRA (PostGIS di GeoServer)** | inventario IFFI, mosaico PAI frane; il mosaico idraulico alimenta la suscettibilità agli allagamenti e il componente `H` delle frane | all'init | `limen geodati-sync` (scarico IdroGEO) + `integrations/geoserver_source/` |
| **Copernicus EWDS — GloFAS** | previsione di portata per nodo (`cems-glofas-forecast`, corsa di controllo) e **piena ordinaria** di ogni nodo (`glofas_riferimento`), il denominatore del rapporto fluviale | previsione 4 volte al giorno, riferimenti di notte | `integrations/copernicus/` |
| **Copernicus Land — EGMS** | moto del suolo Ortho L3: velocità p90 per cella e pixel validi | sincronizzazione annuale + controllo notturno della release | `integrations/egms/` + `limen sync-egms` |
| **Radar DPC** | SRI (1 km / 5 min) come innesco nowcast; cumulata «Merging» su ogni cella per gli allagamenti (#199) | ogni `NOWCAST__INTERVAL_MINUTES` / a ogni giro | `integrations/dpc/` |
| **INGV** | eventi FDSN (mag ≥ 3,5, ultimi 7 giorni); griglia ShakeMap | su evento | `integrations/ingv/` |
| **EFFIS** | perimetri delle aree bruciate (**MapServer** pubblico, senza credenziali) | settimanale | `integrations/effis/` |
| **NASA FIRMS** | fuochi VIIRS/MODIS, innesco NRT + archivio per Paese | ogni `FIRMS__INTERVAL_MINUTES` | `integrations/firms/` |
| **Copernicus EMS** | aree allagate osservate + maschere di osservazione | una tantum | `integrations/copernicus_ems/` |
| **Bootstrap statico** | per cella `iffi_density_500`, `distance_to_iffi_m`, `pai_class_norm`, `slope_deg`, uso del suolo, geologia, WUI; salta le sorgenti invariate (#101) | una tantum | `integrations/static_bootstrap/` |
| **Motore di calcolo (V1)** | soglia I/D di Caine (ritarata su ITALICA), pioggia antecedente sigmoide, finestra post-incendio modulata dalla severità, decadimento sismico, aggregatore pesato + 5 classi | puro (niente I/O) | `core/scoring/` |
| **Registro dei pericoli** | motori registrati per *(pericolo, implementazione)*; un YAML per pericolo | trasversale | `core/scoring/registry.py`, `config/hazards/` |
| **Sfidante ML** | LightGBM con CV a blocchi spaziali; gira in ombra ogni notte; promozione solo a mano | notturno | `ml/` + `limen train` |
| **Previsione** | calcolo a `now+H` con la pioggia prevista; avvisi «PREVISIONE» con il loro dedup | 4 volte al giorno | `agents/workflows/forecast.py` |
| **Sintesi regionali** | testi in italiano e inglese per regione e pericolo, salvati in `spiegazioni_regione`; un testo di ripiego è segnato come tale | asincrono | `api/jobs/briefing_enrichment.py` |
| **MCP `limen-ops`** | `tool_risk_summary`, `tool_top_risk_cells`, `tool_cell_breakdown`, `tool_recent_alerts`, `tool_national_report`, `tool_comune_risk`, `tool_top_comuni` + strumenti admin dietro `MCP_ADMIN_TOKEN` | HTTP `127.0.0.1:8766/mcp` | `mcp/` + `limen mcp-serve` |
| **A2A** | Agent Card JSON-RPC 2.0 su `/.well-known/agent-card.json`, `/a2a` con `message/send`, `message/stream`, task | sola lettura | `a2a/` |
| **Tile vettoriali** | `mv_latest_risk`, `risk_at(z,x,y,hours_ago,hazard)`, `forecast_at(z,x,y,horizon,hazard)` via pg_tileserv | a ogni ciclo | migrazioni `007`, `060` |
| **Aggregato per comune** | `mv_comune_risk`: cella peggiore, profilo per classe, classifica per esposizione; REST `/api/comuni` | a ogni ciclo | migrazione `026_comuni.sql` |
| **Report** | report nazionale giornaliero sui canali di avviso; report HTML statico delle zone più a rischio con archivio immutabile; PDF delle regioni | giornaliero / orario | `api/jobs/`, `report/`, `limen report build` |
| **Notifiche** | protocollo `NotificationChannel`: Telegram, MQTT, e-mail, webhook; invio in parallelo, isolamento per canale, dedup | a ogni tick | `notifications/` |

Tabelle principali: `aoi`, `grid_cells`, `cell_static_factors`,
`risk_assessments` e `model_runs` (partizionate per giorno UTC), `latest_risk`,
`training_samples`, `fwi_state`, `glofas_riferimento`, `glofas_previsione`,
`cell_insar_features`, `spiegazioni_regione`, `alert_dispatches`,
`fire_perimeters`, `landslide_events`, `schema_migrations`. Geometrie in
EPSG:4326; distanze e aree in EPSG:3035. Altro in
[`docs/architecture.md`](./docs/architecture.md) e
[`docs/data-model.md`](./docs/data-model.md).

</details>

<details>
<summary><b>Perché queste scelte</b></summary>

| Decisione | Motivazione |
|-----------|-------------|
| **PostgreSQL 16 + PostGIS indipendente dal motore** (niente BaaS, niente ORM) | Stesso SQL e stesso codice su Docker locale, Neon o self-hosted. Cambia solo `DB__CONNECTION_STRING`. |
| **`asyncpg` + un codec PostGIS proprio** | Le geometrie viaggiano come oggetti Shapely: niente boilerplate WKB. |
| **`pg_cron` opzionale** | Neon non lo supporta; APScheduler fa girare gli stessi job. |
| **Object storage dietro un Protocol** | I byte dei raster non entrano mai nel DB; qualsiasi endpoint S3-compatibile, mai un SDK cloud. |
| **Migrazioni in SQL puro** | Un runner con checksum; stesso comportamento su ogni Postgres. |
| **GeoServer come sorgente dati generica** | mcp-geo-server pubblica i dati ISPRA; la semantica ISPRA vive solo nel loader di Limen. |
| **Dati Copernicus alla fonte** | GloFAS dall'EWDS ed EGMS dall'archivio CLMS: Open-Meteo non può ospitare GloFAS, e la sua cella è un passo a est di quella che dichiara — sul Toce, un fattore dieci. |
| **Un worker, tre cadenze** | Il calcolo orario senza AI sta nel tick; le sintesi sono asincrone; ML e manutenzione girano di notte. |

</details>

---

## Funziona? Cosa abbiamo misurato

Verifichiamo ogni formula su **eventi reali del passato** e pubblichiamo i
numeri, anche quelli scomodi.

<p align="center">
  <img src="docs/images/wildfire-backtest.it.svg" alt="Backtest incendi in Basilicata: nel 2025 il 79% dei giorni con un incendio reale era nella classe alta di Limen, contro un tasso di base del 43%; nel 2024 il 100% contro il 28%." width="100%">
</p>

**Perché due barre.** Un sistema che dice «pericolo» ogni giorno d'estate
prende tutti gli incendi ed è inutile. Per questo ogni verifica riporta il
**tasso di successo** (quante volte un evento reale era stato segnalato)
**accanto al tasso di base** (quante volte il sistema segnala comunque). La
distanza fra i due è la capacità del modello.

| Cosa | Risultato | Rispetto a |
|---|---|---|
| Incendi, Basilicata 2025 (perimetri EFFIS) | **79 %** di successo | 43 % tasso di base |
| Incendi, Basilicata 2024 | **100 %** di successo | 28 % tasso di base |
| Sfidante ML frane (37k campioni, CV a blocchi spaziali) | **AUC-PR 0,60** | 0,28 del motore deterministico |
| Sfidante ML incendi (una stagione, 30.066 campioni) | **AUC-PR 0,352** | 0,237 del solo FWI |
| Soglia di pioggia per le frane ritarata su e-ITALICA | ~95 % delle frane reali sopra soglia | 64 % con la soglia storica |
| Frane reali che raggiungono ≥ Moderata (pioggia da pluviometri) | ~63–77 % | — |

**Dove siamo, onestamente** (#122). Con la pioggia da rianalisi, la classe
**«alta»** delle frane prende ancora poche frane: Liguria, novembre 2019, l'11 %
di 131 frane con lo 0,17 % delle ore-cella in allerta; Marche, maggio 2014,
nessuna di 172. Il punteggio ordina bene le celle dentro una regione, ma il
limite è il segnale di pioggia come lo leggiamo oggi, ed è il prossimo lavoro.
I modelli ML restano **sfidanti** in modalità ombra: il motore deterministico
resta l'unico autorevole finché un modello non lo batte in validazione
incrociata spaziale e nel backtest, e la promozione è una decisione manuale.

Rifai le verifiche da te: `limen backtest`, `limen backtest-flood`,
`limen backtest-wildfire`, `limen verifiche-report`.

---

## Installazione su un server

A Limen serve **solo Docker** sull'host, più il repository e un `.env`. I
comandi `limen` girano dentro il container del worker; i job periodici stanno
nel worker, non nel crontab dell'host.

```sh
git clone https://github.com/agent-engineering-studio/limen.git && cd limen
cp .env.example .env                   # almeno LIMEN_DATA_ROOT (assoluto)
./scripts/nuovo_host.sh --controlla    # solo i prerequisiti, non cambia niente
./scripts/nuovo_host.sh --ripristina   # dal backup notturno (servono le BACKUP__*)
./scripts/nuovo_host.sh --da-zero      # uno stack nuovo: seed, eventi, calibrazione, FWI
```

`--controlla` verifica Docker e Compose, lo spazio libero sotto
`LIMEN_DATA_ROOT` (`NUOVO_HOST_DISCO_GB`, 50) e la **latenza di fsync** del
disco di Docker (`NUOVO_HOST_FSYNC_MS_MAX`, 20 ms): su un disco a ~1 s per
fsync, `initdb` va in timeout. Gli altri due modi si possono rilanciare e
finiscono con `limen data-status` e `limen jobs`.

**Cosa si riempie da solo, e quando.** La mappa: il primo giro orario, entro
l'ora. La previsione per cella: alle 02, 08, 14 e 20:20 UTC. La catena FWI
richiede un mese di spin-up dopo `fwi-backfill`; un ripristino la riporta già
assestata. I riferimenti GloFAS: una parte dei nodi ogni notte, settimane per
tutti.

### Aggiornare la produzione: `make deploy`

La produzione gira da un worktree staccato accanto al checkout di sviluppo
(`../limen-deploy`, `DEPLOY_DIR`), con lo stesso progetto compose, lo stesso
`.env` e gli stessi volumi di `make up`:

```sh
make deploy                       # produzione su origin/main
make deploy DEPLOY_REF=3eadcda    # un commit preciso, anche per tornare indietro
```

Si rifiuta di partire se i test di quel commit non sono verdi sulla CI o se il
worktree ha modifiche locali; altrimenti ricostruisce `api`, `worker`, `mcp`
(e la SPA se `frontend/` è cambiato), aspetta `/ready` e registra il commit in
`refs/deploy/ultimo`. Le migrazioni le applica l'API all'avvio. Mai `make up`
nel checkout di sviluppo sull'host di produzione: condivide il progetto
compose e metterebbe in produzione quello che c'è nel checkout.

<details>
<summary><b>Immagini, dati statici, gateway LLM, reverse proxy</b></summary>

### Immagini: costruite qui o scaricate da GHCR

Di default i file compose **costruiscono** le immagini sull'host. Ogni push su
`main` e ogni tag `vX.Y.Z` le pubblica anche su GHCR, con i tag
`sha-<commit>`, `main`/`latest` e la versione:

```sh
# nel .env
LIMEN_IMAGE_PREFIX=ghcr.io/agent-engineering-studio/limen-
LIMEN_IMAGE_TAG=sha-7a8dd95       # oppure 0.7.0; mai latest su un server
```

Con il prefisso impostato, `make up` scarica invece di costruire, e tornare
indietro è il tag precedente. La SPA pubblicata chiama tutto **sulla sua
stessa origine**, quindi il reverse proxy instrada `/api/` all'API (`:8080`),
`/tiles/` a pg_tileserv (`:7800`) e `/geoserver/ispra/wms` a GeoServer
(`:8081`, solo il WMS). Le immagini sono `linux/amd64`. Le immagini di terzi
sono fissate a una versione (pg_tileserv `20250131`, Open-Meteo `1.6.0`,
mcp-geo-server al suo commit).

### Dati statici

- **Snapshot statico** (#305): `limen static-snapshot export` salva sullo
  store dei backup i fattori per cella già calcolati (invece dei ~47 GB di
  raster da cui derivano); `limen static-snapshot import` li carica su una
  nuova istanza dopo `migrate` e `seed`. Poi `limen calibrate`.
- **`make fetch-static`** scarica quello che non richiede account: il raster
  CLMS del suolo sigillato e strade e ferrovie OSM, con un manifest di
  dimensioni e sha256. DTM, CORINE, geologia e strati ISPRA li scarica il
  passo dei dati statici di `make init` (vedi l'Avvio rapido).
- **`make static-data`** lancia gli stessi comandi sull'host se c'è `uv`,
  altrimenti in un container usa e getta del worker.

### Gateway LLM senza GPU

`make inference-up-cpu` avvia LiteLLM e un servizio di embedding su CPU, con
gli stessi nomi di modello dello stack GPU. Senza una chiave cloud le sintesi
ripiegano su un testo deterministico: **la mappa e gli avvisi non dipendono
mai da un LLM.** Vedi [`docs/inference.md`](./docs/inference.md).

### Reverse proxy e certificati

Imposta `LIMEN_DOMINIO` e `make up` aggiunge Caddy su 80 e 443 con i
certificati Let's Encrypt e le stesse rotte di
[`infra/nginx/`](./infra/nginx/). Senza, usa il tuo proxy.

</details>

### Porte pubblicate: Docker scavalca ufw

Docker scrive le sue catene iptables, consultate *prima* di quelle di ufw: il
`default deny incoming` dell'host **non** protegge una porta pubblicata da un
container. Per questo ogni voce `ports:` si lega a una variabile
`LIMEN_*_BIND` che vale `127.0.0.1` di default (`LIMEN_PG_BIND`,
`LIMEN_API_BIND`, `LIMEN_MQTT_BIND`, `LIMEN_TILESERV_BIND`,
`LIMEN_FRONTEND_BIND`, `LIMEN_MCP_BIND`, `LIMEN_GEOSERVER_*_BIND`,
`LIMEN_GEODATA_*_BIND`). L'esposizione pubblica passa da un reverse proxy sulla
443, mai legando una porta a `0.0.0.0`.

---

## Backup e ripristino

Limen salva il suo **stato** ogni notte, fuori dal server. Il database pesa
circa 31 GB, ma quasi tutto si può ricostruire; quello che non si può sta in
~2 GB (eventi verificati, campioni di addestramento, dati dei sensori, sintesi,
avvisi, la catena FWI, i riferimenti GloFAS). Misurato sui dati di
produzione: un dump da **202 MB** in **41 s**, ripristinato e verificato in
**62 s**.

```sh
make backup                      # un backup adesso, dal worker
make backup-elenco               # i backup completi sul bucket
make restore CONFERMA=1          # ripristina l'ultimo (API e worker fermi)
make restore CONFERMA=1 CHIAVE=backup/2026-10-24T02-05-00Z/
uv run limen sensore ripristina-ca --dove "$LIMEN_SENSORI_DIR"   # CA dei sensori, sull'host
```

<details>
<summary><b>Cosa si salva, cosa rifiuta il ripristino, il ripristino a mano</b></summary>

Il passo `backup` del job notturno scrive `backup/<ora UTC>/` su un bucket
S3-compatibile dedicato (`BACKUP__*`, separato da `OBJECT_STORE__*`):

| File | Contenuto |
|---|---|
| `limen.dump` | `pg_dump --format=custom`: lo schema di ogni tabella; i dati di tutte tranne `BACKUP__SOLO_SCHEMA` (calde, derivate o ricaricabili) |
| `mlflow.dump` | il registro MLflow, quando è un database PostgreSQL sullo stesso server |
| `ruoli.sql` | i ruoli senza password (i ruoli ristretti le prendono da `DB__*_PASSWORD`) |
| `mlruns.tar.gz` | le cartelle di `BACKUP__CARTELLE` (gli artefatti MLflow) |
| `manifest.json` | scritto per ultimo: dimensioni, sha256 e **numero di righe di ogni tabella salvata**; un backup senza è stato interrotto |

I backup più vecchi di `BACKUP__RETENTION_GIORNI` (30) si cancellano, ma gli
ultimi `BACKUP__TIENI_ALMENO` (3) restano sempre, e un backup con meno della
metà delle righe del precedente sospende la cancellazione. Un ultimo backup
riuscito più vecchio di `BACKUP__ETA_MASSIMA_ORE` (36) produce nei log
`integration.degraded label=backup.stale`.

La **CA dei sensori** si salva cifrata (scrypt + AES-256-GCM, passphrase in
`BACKUP__PASSPHRASE_CA`). **Tieni una copia della passphrase fuori dal
server**: senza, il backup della CA non si apre.

**Cosa rifiuta il ripristino:** un ripristino che non trova tutte le righe
promesse dal manifest; un database con altri client collegati; un database a
una migrazione diversa da quella del backup (`--forza` scavalca gli ultimi
due).

**A mano, in ordine:** (1) Docker, repo e `.env` con le `BACKUP__*`;
(2) `make db-up`; (3) `make restore CONFERMA=1`; (4) se gestisci la rete dei
sensori, `limen sensore ripristina-ca`, `make sensori-ca-init`,
`make sensori-up`; (5) `make up`; (6) aspetta il giro orario e ricarica gli
strati ISPRA con `make static-data`; (7) controlla con `limen data-status`,
`limen jobs` e la mappa. `./scripts/nuovo_host.sh --ripristina` fa i passi
2–5.

Non incluso: l'archivio radar locale (`RADAR_ARCHIVE__CARTELLA`, ~51 GB;
aggiungilo a `BACKUP__CARTELLE` se ti servono i mesi più vecchi).

</details>

---

<details>
<summary><b>Gruppi di dipendenze Python</b></summary>

Tutto passa da `uv` (`uv sync --all-groups` per il set completo). Le
dipendenze di runtime sono in `pyproject.toml`; quelle opzionali sono
raggruppate per chi le usa:

| Gruppo | Per | Pacchetti principali |
|---|---|---|
| _(runtime)_ | API, worker, CLI | asyncpg, shapely, geopandas, rasterio, pydantic, httpx + tenacity, APScheduler, FastAPI, structlog, OpenTelemetry, le librerie estratte |
| `ml` | motore ML V2, addestramento, drift | LightGBM, scikit-learn, MLflow, Optuna, SHAP, ONNX Runtime |
| `dl` | esperimenti di deep learning | PyTorch, ONNX |
| `agents` | il revisore di fedeltà in Message Batch | anthropic |
| `mcp` | server MCP | fastmcp |
| `report` | report PDF/HTML | Jinja2, ReportLab |
| `copernicus` | EWDS (GloFAS, confronto FWI) | cdsapi, netCDF4 |
| `radar` | archivio radar DPC | numcodecs |
| `storage` | object store S3-compatibile | boto3 (importato solo dalla factory dell'object store) |
| `dev` | test e gate | pytest, ruff, mypy, testcontainers, respx |

</details>

## Test e quality gate

```bash
make check                 # il gate: lint + typecheck + test (copertura ≥ 80 %) + link della doc
make test-unit             # veloci, senza Docker
make test                  # unit + integrazione (testcontainers)
make test-slow             # test con il seme nazionale (esclusi di default)
make lint && make format   # ruff
make typecheck             # mypy --strict su src/
( cd frontend && npm test && npm run lint )
```

Su Apple Silicon imposta `LIMEN_TEST_POSTGIS_IMAGE=imresamu/postgis-arm64:16-3.5`;
`LIMEN_TEST_DATABASE_URL` fa puntare i test a un PostGIS già esistente.

---

## Stato e roadmap

**Fatto:** tre pericoli in produzione su tutte le 20 regioni; una previsione a
72 ore per cella quattro volte al giorno; italiano e inglese; dati Copernicus
alla fonte (GloFAS dall'EWDS, EGMS dall'archivio CLMS); una pagina «Regioni da
monitorare» con i report in PDF; inneschi dal radar DPC e dai fuochi NASA
FIRMS; uno sfidante ML in ombra ogni notte con diagnostica pubblica;
interfacce MCP e A2A per gli agenti AI; avvisi via webhook; una rete aperta di
sensori; backup notturni fuori sede.

**Prossimi passi:**
- **Il segnale di pioggia per le frane** (#122): intensità oraria contro
  cumulata, la finestra di 48 ore, soglie di Caine per macro-regione — tarando
  sempre su un gruppo di regioni e verificando sulle altre.
- **Verdetto dell'ombra** dello sfidante ML (`limen shadow-report`); la
  promozione resta manuale.
- **Diagramma di affidabilità** per la diagnostica ML, quando ci saranno
  abbastanza eventi reali (#30).

Vedi [`ROADMAP.md`](./ROADMAP.md) e [`CHANGELOG.md`](./CHANGELOG.md).

<details>
<summary><b>Scelte di progetto da conoscere</b></summary>

- **Nessuna autenticazione utente, per scelta** (epic #69). Limen è una mappa
  pubblica: tutte le API che la alimentano sono sempre state pubbliche, quindi
  un login proteggeva la pagina, non i dati. L'unica azione privilegiata,
  lanciare un giro di calcolo, sta sulla CLI (`limen monitor-once`) e su MCP
  dietro `MCP_ADMIN_TOKEN`.
- **Il motore deterministico resta il campione.** Non si toglie e non si
  indebolisce mai; un modello ML deve batterlo in CV a blocchi spaziali e nel
  backtest, e un operatore lo promuove a mano.
- **Agenti.** `limen mcp-serve` espone rischio, avvisi e report come strumenti
  MCP (OpenClaw, Claude Desktop):
  `openclaw mcp set limen-ops '{"url":"http://127.0.0.1:8766/mcp","transport":"streamable-http"}'`.
  Gli avvisi si possono anche spingere a un gateway per agenti via webhook.

</details>

---

## Licenze e attribuzioni

### Il codice

| Componente | Licenza |
|---|---|
| **Limen** (questo repository) | [EUPL-1.2](./LICENSE) — copyleft che copre anche l'uso in rete: chi offre Limen come servizio deve pubblicare le sue modifiche. Le versioni fino a `v0.6.0-impl-complete` restano Apache-2.0. È disponibile una licenza commerciale per usi incompatibili con il copyleft. |
| copernicus-ems, egms-client, firms-client, ispra-idrogeo, fwi-chain, effis-client, rainfall-thresholds | Apache-2.0 |
| mcp-geo-server | MIT |

I contributi esterni richiedono il CLA descritto in
[`CONTRIBUTING.md`](./CONTRIBUTING.md#contributor-license-agreement).

### I dati

L'attribuzione è **obbligatoria** quando si pubblicano la mappa, le sintesi o
qualsiasi cosa ne derivi:

* **ISPRA IdroGEO** (IFFI, mosaici PAI frane e idraulica) — © ISPRA,
  CC-BY 4.0. <https://idrogeo.isprambiente.it>
* **e-ITALICA** (CNR-IRPI) — CC-BY 4.0, DOI
  [10.5281/zenodo.14204473](https://doi.org/10.5281/zenodo.14204473).
* **Open-Meteo** (ECMWF, DWD, Copernicus ERA5 / CERRA) — CC-BY 4.0.
  <https://open-meteo.com>
* **Copernicus EMS — GloFAS** — licenza CEMS-Floods: chi pubblica dati
  derivati deve riportare **«Contains modified Copernicus Emergency
  Management Service information [anno]»** e non deve presentarli come
  un'allerta alluvione. Limen lo fa sulla mappa, nel piè di pagina della home,
  negli articoli sugli allagamenti e nel PDF delle regioni
  (`frontend/src/lib/attribuzioni.ts`, `report/regioni_pdf.py`). I dati EFAS
  in tempo reale soggetti all'art. 12 del Reg. (UE) 1159/2013 non si
  ripubblicano. <https://ewds.climate.copernicus.eu>
* **Copernicus EMS — CEMS Fire** (`cems-fire-historical-v1`) — CC-BY 4.0.
* **Copernicus EMS Rapid Mapping** — © Unione europea, libero con
  attribuzione. <https://rapidmapping.emergency.copernicus.eu>
* **Copernicus Land — EGMS** e impermeabilizzazione — licenza aperta
  Copernicus Land (Reg. UE 2021/696): citare «Generated using European Union's
  Copernicus Land Monitoring Service information» e indicare le modifiche.
  <https://egms.land.copernicus.eu>
* **INGV** (eventi FDSN, ShakeMap, TINITALY) — CC-BY 4.0. <https://terremoti.ingv.it>
* **EFFIS** (perimetri delle aree bruciate, FWI) — condizioni Copernicus EFFIS.
* **NASA FIRMS** — uso libero con citazione: «We acknowledge the use of data
  and imagery from LANCE FIRMS operated by NASA's Earth Science Data and
  Information System (ESDIS) with funding provided by NASA Headquarters.»
  <https://firms.modaps.eosdis.nasa.gov>
* **Piattaforma radar DPC** (SRI, «Merging») — CC-BY-SA 4.0.
* **CORINE Land Cover 2018 Italia** (SINAnet/ISPRA) — CC-BY.
* **Carta geolitologica d'Italia 1:500k** (PCN/MASE) — CC-BY 4.0.
* **ISTAT** (confini amministrativi 2023) — CC-BY.
* **OpenStreetMap** (mappa di base, strade, ferrovie) — © OpenStreetMap
  contributors, ODbL.

---

## Sostieni Limen

Limen è sviluppato e ospitato da [Agent Engineering Studio](https://www.agentengineering.it)
su un server proprio, senza pubblicità e senza raccolta di dati personali.
L'autunno porta le piogge, e le piogge portano frane e alluvioni: è il momento
in cui una mappa aperta del pericolo serve di più.

* ⭐ **Metti una stella** a questo repository (e alle
  [librerie](#le-librerie-collegate)): aiuta chi lavora su protezione civile,
  geologia e dati aperti a trovarlo.
* 🔁 **Condividi** la [mappa](https://limen.agentengineering.it/) e dicci, con
  una issue, dove il pericolo stimato non ti sembra giusto.
* ☕ **Offrici un caffè**: copre il server, gli archivi meteo e il tempo per
  tarare il motore sui dati reali.

  <a href="https://www.buymeacoffee.com/f9t3zol"><img src="https://img.buymeacoffee.com/button-api/?text=Offrimi%20un%20caff%C3%A8&emoji=&slug=f9t3zol&button_colour=FFDD00&font_colour=000000&font_family=Cookie&outline_colour=000000&coffee_colour=ffffff" alt="Offrimi un caffè" height="40"></a>
* 🏛️ **Enti pubblici, comuni, università**: per sperimentazioni sul vostro
  territorio, scriveteci da [agentengineering.it](https://www.agentengineering.it).

## Come è stato costruito

Limen è sviluppato con [Claude Code](https://claude.com/claude-code) dal primo
commit, il 3 giugno 2026: la maggior parte dei commit è scritta insieme a
Claude, come dice la riga `Co-Authored-By` di ognuno. Le sintesi regionali sono
scritte con Claude, il modello di Anthropic, e non cambiano nessun numero.
Limen è un progetto indipendente, non affiliato ad Anthropic.

## Contribuire e governance

* [`CONTRIBUTING.md`](./CONTRIBUTING.md) — ambiente di sviluppo, stile dei commit, gate, CLA.
* [`SECURITY.md`](./SECURITY.md) — segnalazioni private; modello delle
  minacce in [`.oss-scanner/threat_model.md`](./.oss-scanner/threat_model.md).
* [`CODE_OF_CONDUCT.md`](./CODE_OF_CONDUCT.md) · [`ROADMAP.md`](./ROADMAP.md) ·
  [`CHANGELOG.md`](./CHANGELOG.md) · [`docs/OSS_IMPACT.md`](./docs/OSS_IMPACT.md)
* Documentazione di dettaglio: [`docs/architecture.md`](./docs/architecture.md),
  [`docs/scoring-model.md`](./docs/scoring-model.md),
  [`docs/api.md`](./docs/api.md), [`docs/deployment.md`](./docs/deployment.md),
  [`docs/runbook.md`](./docs/runbook.md), [`docs/inference.md`](./docs/inference.md),
  [`docs/openclaw.md`](./docs/openclaw.md).

## Licenza

Copyright © 2026 Giuseppe Zileni. Limen è un progetto personale, sviluppato
al di fuori di qualsiasi rapporto di lavoro e con mezzi propri dell'autore:
il titolare dei diritti è l'autore, che è anche la parte a cui il CLA concede
le licenze. Codice sotto [EUPL-1.2](./LICENSE); vedi
[Licenze e attribuzioni](#licenze-e-attribuzioni).
