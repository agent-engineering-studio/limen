# Integrazioni: API, MCP & A2A

**Limen si lascia leggere da altri sistemi in cinque modi: un'API REST
pubblica, le tile vettoriali della mappa, due server MCP per i gateway
agentici, il protocollo A2A per l'interoperabilità tra agent e le notifiche
push verso canali esterni.** Tutti sono di sola lettura sul punteggio:
nessuna integrazione può alterare un valore di rischio, e le poche azioni
che scrivono (lanciare un monitoraggio, rigenerare un report) stanno dietro
un token amministrativo che, se non è impostato, le spegne.

## Panoramica: cinque modi di leggere Limen

| Superficie | Per chi | Dove | Autenticazione |
|---|---|---|---|
| API REST | applicazioni, script, dashboard | `/api/...` sulla porta 8080 (default) | nessuna |
| Tile vettoriali | mappe web (MapLibre, OpenLayers, QGIS) | pg_tileserv, oppure il proxy `/api/tiles/...` | nessuna |
| MCP `limen-ops` e `ispra-geo` | gateway agentici (OpenClaw, Claude Desktop, …) | `:8766/mcp` e `:8765/mcp` | lettura aperta; scrittura con `MCP_ADMIN_TOKEN` |
| A2A | agent di terze parti | `/.well-known/agent-card.json` + `POST /a2a` | nessuna (solo lettura) |
| Notifiche push | Telegram, MQTT, email, webhook | configurate lato server | il canale stesso |

Tutte leggono gli stessi numeri: quelli che il motore deterministico ha
scritto nell'ultimo giro orario. Nessuna superficie ricalcola un punteggio
al momento della richiesta, quindi due client che chiedono la stessa cella
nello stesso momento ricevono lo stesso valore.

## API REST

**Un'API HTTP/JSON pubblica, senza login, documentata anche in formato
OpenAPI su `/docs`, `/redoc` e `/openapi.json`.** È la stessa che usa la
mappa: non esiste un'API «interna» più ricca di quella pubblica.

Regole comuni a tutte le rotte:

- **Il pericolo** si sceglie con `hazard`, che accetta `landslide`, `flood`
  o `wildfire`; se manca vale `landslide`. Un valore diverso è un `422`.
  Quali pericoli sono attivi in una data installazione lo dice
  `GET /api/hazards`.
- **Le classi** sono cinque: `None`, `Low`, `Moderate`, `High`, `VeryHigh`
  (nessuno, basso, moderato, alto, molto alto); i punteggi vanno da 0 a 1.
- **«Non misurato» non è «calmo».** Quando il segnale dinamico di un
  pericolo non è arrivato (la fonte meteo era giù, per esempio) il
  punteggio vale 0 come quello di una cella tranquilla; per distinguerli le
  risposte portano `measured: false`. Un client che mostra il punteggio
  senza guardare `measured` può dire «nessun pericolo» dove Limen dice «non
  lo so».
- **Degrado.** Quando una fonte esterna manca, le rotte di lettura
  rispondono comunque `200` con un campo vuoto (`null` o `[]`), mai con un
  errore; un `404` vuol dire che la cella, il comune o la regione non
  esistono.
- **Cache.** Molte rotte dichiarano `Cache-Control` (da 30 secondi a un
  giorno): il dato cambia al più una volta l'ora, quindi interrogarle più
  spesso non porta niente di nuovo.
- **Lingua.** Le rotte non hanno un parametro di lingua: i testi arrivano
  con il suffisso della lingua (`briefing_it`, `briefing_en`).

Esempio:

```
curl -s 'http://127.0.0.1:8080/api/aoi/it-puglia/risk/latest?hazard=flood'
```

### Territorio e pericoli

| Rotta | Cosa restituisce |
|---|---|
| `GET /api/aoi` | Le aree monitorate (`id`, `name`, `kind`): una per regione. |
| `GET /api/hazards` | I pericoli calcolabili in questa installazione (`hazard`, `label_it`) e quello di default. |
| `GET /api/legend?hazard=` | Le cinque classi con i loro estremi di punteggio (`lo`, `hi`), il livello di allerta corrispondente e la scheda del modello. Le soglie vengono dallo YAML del pericolo, non sono scritte nel client. |

### Rischio per area e per cella

| Rotta | Cosa restituisce |
|---|---|
| `GET /api/aoi/{aoi_id}/risk/latest?hazard=` | L'ultima valutazione di una regione: ogni cella con punteggio, classe e scomposizione, i conteggi per classe e il racconto (`briefing_it`/`briefing_en`). `briefing_is_fallback: true` vuol dire che il testo è quello deterministico, non quello scritto dall'AI. `404` se la regione non ha ancora valutazioni per quel pericolo. |
| `GET /api/cell/{cell_id}/breakdown?hazard=` | Lo stato attuale di una cella: punteggio, classe, fattori che lo compongono, spiegazione e `measured`. |
| `GET /api/cell/{cell_id}/multi-hazard` | I tre pericoli insieme per una cella: il peggiore, quanti sono almeno moderati e quanti almeno alti, e il dettaglio di ognuno. |
| `GET /api/cell/{cell_id}/history?hazard=&hours=72` | Serie osservata (ultime `hours` ore) e serie prevista (+24/48/72 h) della cella. Una cella sconosciuta dà due liste vuote, non un `404`. |
| `GET /api/cell/{cell_id}/rain-outlook` | Pioggia prevista nelle prossime 48 ore: totale in mm e picco orario. `outlook: null` se la fonte meteo non risponde. |
| `GET /api/cell/{cell_id}/rain-models` | La pioggia delle prossime 72 ore secondo cinque modelli meteo diversi (ICON, Météo-France, ECMWF IFS, GFS, ECMWF AIFS), dal più asciutto al più bagnato: quanto i modelli sono d'accordo. |
| `GET /api/cell/{cell_id}/fwi-normale?fwi=&month=` | Quanto è insolito un valore dell'indice di pericolo incendi (FWI) per quel mese in quel punto: percentile, mediana e 90° percentile della climatologia locale. `normale: null` dove la climatologia non c'è. |

### Comuni e regioni

| Rotta | Cosa restituisce |
|---|---|
| `GET /api/comuni?hazard=&aoi=&q=&order=now&limit=50` | I comuni da tenere d'occhio, dal più urgente: per ogni comune la classe peggiore, i dettagli per pericolo, la previsione a +24/48/72 h, l'allerta ufficiale del giorno se importata, e l'indice di attenzione (`attention`). Compaiono solo i comuni almeno moderati, salvo una ricerca per nome con `q`. Con `hazard` soglia e ordine guardano solo quel pericolo; con `order=forecast` l'ordine segue la previsione. |
| `GET /api/comune/{istat_code}` | Un comune con le sue celle. `404` se il codice ISTAT non esiste. |
| `GET /api/comune/{istat_code}/geometry` | Il confine del comune in GeoJSON. |
| `GET /api/comune/{istat_code}/history?hours=168` | Serie osservate e previste per pericolo, per i grafici di tendenza. |
| `GET /api/regioni` | Il quadro per regione, dalla più da guardare: pericoli, previsione, comuni, allerta ufficiale di oggi e domani, e il racconto per pericolo con le traduzioni. |
| `GET /api/regioni/rapporto.pdf?aoi=` | Il rapporto PDF di una regione, o di tutte senza `aoi`. Ogni pagina porta l'attribuzione Copernicus. |

L'indice di attenzione di un comune è il più alto tra i pericoli
*misurati*, con un incremento quando più pericoli sono insieme sopra soglia:
non è una somma, e un pericolo non misurato non lo abbassa. Se nessun
pericolo è misurato, `attention` è `null`, non zero.

### Allerte e previsione

| Rotta | Cosa restituisce |
|---|---|
| `GET /api/alerts?hazard=&threshold=High&since_hours=72&limit=200` | Le celle a quella classe o sopra, ordinate per priorità (punteggio pesato per l'esposizione: case, strade, servizi), con il nome del comune. Una soglia non riconosciuta viene letta come `High`. |
| `GET /api/alerts/forecast?hazard=&since_hours=72&limit=50` | Gli avvisi di previsione inviati: regione, pericolo, orizzonte, classe massima, celle coinvolte e testo. Senza `hazard`, tutti i pericoli. |
| `GET /api/alerts/forecast/schedule` | Quando gira la prossima previsione per cella e quando è girata l'ultima per ogni pericolo. |

### Spiegazioni e provenienza

| Rotta | Cosa restituisce |
|---|---|
| `GET /api/aoi/{aoi_id}/spiegazione?hazard=` | Il racconto dell'AI per una regione: testo, modello, ora in cui è stato scritto, analisi. `spiegazione: null` quando non c'è, oppure quando il modello non ha risposto: il testo di ripiego deterministico non viene mai attribuito all'AI. |
| `GET /api/report/national?hazard=` | Il quadro nazionale aggregato: totali, celle più a rischio, sezione per ogni pericolo e cascate tra pericoli. `hazard` sceglie il pericolo che guida i totali. |
| `GET /api/provenienza` | Da dove vengono i numeri *in questa installazione*: quale motore calcola, se lo sfidante ML gira in ombra, quale modello meteo e quale modello linguistico scrive i racconti. È configurazione letta dal vivo, non una descrizione. |

### Diagnostica e salute

| Rotta | Cosa restituisce |
|---|---|
| `GET /api/status/jobs` | L'ultimo giro orario nazionale (inizio, fine, esito, durata) e lo stato per regione. |
| `GET /api/shadow/summary?aoi=&since=` | Quanto il modello ML sfidante diverge dal motore campione, per regione, e il confronto sugli eventi reali. `since` in ISO 8601. Lo sfidante non guida mai gli avvisi. |
| `GET /api/shadow/reliability?aoi=&since=` | La curva di affidabilità dello sfidante. `sufficient: false` quando gli eventi reali sono troppo pochi per tracciarla. |
| `GET /health` | Sempre `200`; `status: degraded` se il database o la cache non rispondono. |
| `GET /ready` | `503` finché l'API non è pronta: è pensata per l'orchestratore dei container. |

### Inviare un contributo

`POST /api/contributi` è l'unica rotta pubblica che accetta dati: una
segnalazione su una cella (una frana non censita, un parere sulla
valutazione, sui pesi o sulle soglie, una mitigazione). Il corpo è JSON con
`cell_id`, `tipo`, `testo` (da 20 a 4.000 caratteri), un'email e un nome o
un profilo LinkedIn, e il consenso esplicito; un campo sconosciuto è un
`422`. Il contributo **non viene salvato**: parte per email ai curatori del
progetto, con lo stato attuale della cella, e la risposta `201` arriva solo
dopo l'invio. Gli invii sono limitati per indirizzo e in totale ogni ora
(oltre il limite, `429`); senza un server di posta configurato la rotta
risponde `503`. Un contributo non cambia mai un punteggio.

## Tile vettoriali

**La mappa è fatta di tile vettoriali (Mapbox Vector Tile) servite da
pg_tileserv direttamente dal database: chiunque può disegnare le stesse
celle in un'altra mappa.** Ogni sorgente è una vista o una funzione SQL;
il percorso è `/{sorgente}/{z}/{x}/{y}.pbf`, con i parametri nella query
string.

| Sorgente | Parametri | Proprietà di ogni elemento |
|---|---|---|
| `public.v_risk_tiles` | — (solo frane) | `cell_id`, `aoi_id`, `risk_score`, `risk_level`, `computed_at`, `measured` |
| `public.risk_at` | `p_hazard` (default `landslide`), `hours_ago` (default 0) | `cell_id`, `risk_score`, `risk_level`, `measured` |
| `public.multi_hazard_at` | nessuno | `cell_id`, `worst_hazard`, `worst_level`, `worst_score`, `measured`, `hazards_scored`, `hazards_at_high` |
| `public.forecast_at` | `p_horizon` (24, 48 o 72; default 24), `p_hazard` (vuoto = il peggiore) | `cell_id`, `risk_score`, `risk_level`, `worst_level`, `worst_hazard`, `target_at` |
| `public.v_region_tiles` | — (solo frane) | `aoi_id`, `name`, `cells`, `moderate`, `high_or_above`, `max_score`, `risk_level` |
| `public.v_comune_tiles` | — | `istat_code`, `name`, `worst_hazard`, `worst_class`, `max_score`, `attention`, `measured` |
| `public.v_dpc_allerte_oggi` | — | `zona`, `livello` (0 verde … 3 rosso), `emesso`: l'allerta ufficiale del giorno |

Tre cose da sapere per usarle bene:

- `risk_at` con `hours_ago` maggiore di zero rilegge il passato: è così che
  la mappa scorre indietro nel tempo.
- `forecast_at` contiene **solo le celle almeno moderate**: una cella
  assente non è «calma», è sotto soglia nella previsione.
- Le celle con `measured: false` vanno disegnate come quelle non valutate
  (la mappa usa lo stesso grigio), non con il colore della classe più bassa.

L'API offre anche un proxy, `GET /api/tiles/{layer}/{z}/{x}/{y}.pbf`,
che inoltra `p_hazard`, `hours_ago` e `properties`. Il proxy non inoltra
`p_horizon`: per scegliere l'orizzonte della previsione si interroga
pg_tileserv direttamente. Se pg_tileserv non è configurato il proxy
risponde `503`, se non è raggiungibile `502`.

## MCP — chiedere dati e azioni a Limen

Il [Model Context Protocol](https://modelcontextprotocol.io) espone Limen
come «strumenti» che un gateway (OpenClaw, Claude Desktop, …) può chiamare.
I server MCP sono due; entrambi parlano `stdio` per default e HTTP
streamable con `--transport http`.

### `limen-ops` · `http://127.0.0.1:8766/mcp`

Si avvia con `limen mcp-serve --transport http`; host e porta si cambiano
con `LIMEN_MCP_HTTP_HOST` e `LIMEN_MCP_HTTP_PORT`. Il parametro `hazard`,
dove c'è, accetta gli stessi valori dell'API e se manca vale `landslide`.

Strumenti di lettura (aperti):

| Strumento | Cosa fa |
|---|---|
| `tool_hazards()` | I pericoli calcolabili in questa installazione: da chiamare prima di passare `hazard`. |
| `tool_risk_summary(aoi_id?, hazard?)` | Ultimo assessment per regione: celle valutate, celle almeno moderate e almeno alte, punteggio max. |
| `tool_top_risk_cells(limit?, aoi_id?, hazard?)` | Classifica delle celle a rischio più alto (default 10, massimo 100). |
| `tool_cell_breakdown(cell_id, hazard?)` | Scomposizione dei fattori + spiegazione di una cella. |
| `tool_recent_alerts(threshold?, since_hours?, limit?, hazard?)` | Celle sopra soglia nella finestra recente (default `Moderate`, 24 ore, 50 celle). |
| `tool_multi_hazard_summary(cell_id?, aoi_id?)` | I tre pericoli insieme per una cella o per una regione: se ne dà uno solo dei due. |
| `tool_comune_risk(istat_code)` | Il quadro di un comune su tutti i pericoli, con l'indice di attenzione. |
| `tool_top_comuni(limit?, aoi_id?)` | I comuni da tenere d'occhio, ordinati per attenzione (default 10). |
| `tool_national_report()` | Quadro nazionale aggregato + testo pronto in `report_it` e `report_en`; accetta `hazard` per scegliere il pericolo che guida i totali. |

Strumenti di scrittura (abilitati solo da `MCP_ADMIN_TOKEN`: variabile non
impostata ⇒ disabilitati, e lo strumento risponde con un errore invece di
agire):

| Strumento | Cosa fa |
|---|---|
| `tool_run_monitor(aoi_id, admin_token)` | Lancia il workflow di monitoraggio una volta (accetta anche `cell_limit` e `hazard`). |
| `tool_build_report(admin_token)` | Genera il report HTML statico on-demand (idempotente). |
| `tool_forecast_history(admin_token, aoi_ids?)` | Persiste il trend di previsione (+24/48/72h) per i grafici UI. |

### `ispra-geo` · `http://127.0.0.1:8765/mcp` (profilo geodata)

Dati geografici ISPRA (PAI / IFFI). Attivo solo sul VPS, si avvia con
`limen geodata mcp --transport http`:

| Strumento | Cosa fa |
|---|---|
| `tool_hazard_at(lat, lon)` | Classe di pericolosità PAI + autorità + regione in un punto. |
| `tool_iffi_query(bbox o region, movement_type?, limit?)` | Frane del catalogo IFFI in un'area (una sola tra `bbox` e `region`; massimo 500). |
| `tool_pai_summary(region / bbox)` | Distribuzione area/conteggio per classe PAI. |
| `tool_dataset_status()` | Stato dei dataset ISPRA caricati: origine, ultimo aggiornamento, righe. |
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

(`/.well-known/agent.json` è un alias per i client più vecchi.) Dichiara
`streaming: true` e `pushNotifications: true`, e le skill disponibili (le
stesse query di lettura di `limen-ops`; le azioni di scrittura restano solo
su MCP):

| Skill | Cosa fa |
|---|---|
| `national_report` | Sintesi nazionale (default se nessuna skill è indicata). |
| `risk_summary` | Sintesi per regione (param `aoi_id`, `hazard`). |
| `top_risk_cells` | Celle a rischio più alto (param `limit`, `aoi_id`, `hazard`). |
| `cell_breakdown` | Scomposizione di una cella (param `cell_id`, `hazard`). |
| `recent_alerts` | Allerte recenti (param `threshold`, `since_hours`, `limit`, `hazard`). |
| `top_comuni` | Comuni da tenere d'occhio (param `limit`, `aoi_id`). |
| `comune_risk` | Il quadro di un comune (param `istat_code`). |

L'endpoint JSON-RPC 2.0 è `POST /a2a`. Una skill si seleziona con un
`DataPart` (o nei `metadata` del messaggio); senza nulla, o con una skill
sconosciuta, il server risponde con il quadro nazionale:

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

Il risultato arriva come `DataPart`; quando c'è un testo pronto
(`report_it`) lo precede una `TextPart`. Altri metodi: `tasks/get` e
`tasks/cancel` (polling e annullamento), `tasks/pushNotificationConfig/set`
e `/get` per farsi notificare via webhook al termine del task: Limen manda
il task completo all'URL indicato, con il token come `Authorization:
Bearer`.

## Notifiche push

**Quando un giro orario trova celle sopra soglia, Limen può avvisare da
solo, senza che nessuno lo interroghi.** I canali sono quattro: Telegram,
MQTT, email e webhook; si accendono elencandoli in
`NOTIFICATIONS__ENABLED_CHANNELS` e configurando ciascuno con le sue
variabili `NOTIFICATIONS__TELEGRAM__*`, `__MQTT__*`, `__EMAIL__*`,
`__WEBHOOK__*`. Senza canali elencati non parte niente.

Cosa decide se un avviso parte:

- **la soglia**: almeno `Moderate` per default (`ALERT__MIN_LEVEL`); sotto
  `High` una cella deve anche avere una propensione del terreno di almeno
  0,5, perché un moderato su terreno stabile non è una notizia;
- **niente ripetizioni**: la stessa cella non viene riavvisata entro 180
  minuti (`ALERT__DEDUP_WINDOW_MINUTES`); gli avvisi di previsione non si
  ripetono per la stessa regione e lo stesso orizzonte entro 24 ore;
- **niente raffiche**: al massimo 6 messaggi l'ora per canale; quelli in
  più confluiscono in un riepilogo. Un `VeryHigh` passa sempre, subito;
- **per comune**: le celle sono raggruppate per comune, così il messaggio
  dice *dove*, non elenca codici di cella.

Il testo degli avvisi è **deterministico**: costruito dai numeri del
motore, senza un modello linguistico nel percorso. Un avviso non inventa
cifre e non cambia formulazione da un giorno all'altro a parità di dati.

Il webhook manda `{"text", "message", "payload"}`: `text` e `message` sono
lo stesso riassunto in italiano (per gli hook `/hooks/wake` e
`/hooks/agent` di OpenClaw), `payload` è l'avviso completo — regione,
pericolo, classe e punteggio massimi, celle con priorità e comune,
riepilogo per comune, eventuali cascate tra pericoli e link alla mappa.

## Dati aperti e licenze

**Il codice di Limen è rilasciato sotto EUPL-1.2; i dati che usa restano
sotto le licenze delle loro fonti, e chi ripubblica quello che Limen
produce si porta dietro le stesse attribuzioni.** Le principali:

| Fonte | Licenza |
|---|---|
| ISPRA IdroGEO (PAI, IFFI, pericolosità idraulica) | CC-BY 4.0 |
| Open-Meteo (previsioni e archivio ERA5) | CC-BY 4.0 |
| INGV (terremoti) | CC-BY 4.0 |
| Protezione Civile (bollettini di allerta) | CC-BY 4.0 |
| Confini ISTAT | CC-BY 4.0 |
| CORINE Land Cover | CC-BY |
| OpenStreetMap | ODbL |
| GloFAS ed EFAS (Copernicus CEMS-Floods) | licenza CEMS, con dicitura obbligatoria |

**Per l'alluvione la dicitura Copernicus è obbligatoria.** Ogni superficie
che mostra punteggi di alluvione derivati da GloFAS deve riportare:
«Contiene informazioni modificate del Copernicus Emergency Management
Service, [anno]» («Contains modified Copernicus Emergency Management
Service information [Year]»), e non deve presentare il risultato come un
avviso di piena: l'allertamento spetta alle autorità nazionali e regionali.
Il rapporto PDF e la mappa la portano già; chi integra l'API o le tile in
un'altra applicazione la deve aggiungere.

L'elenco completo, con le condizioni di ciascuna fonte, è nel
[README](https://github.com/agent-engineering-studio/limen/blob/main/README.md#attribution-and-open-licences).

## Setup rapido

Lo script idempotente
[scripts/setup_openclaw.sh](https://github.com/agent-engineering-studio/limen/blob/main/scripts/setup_openclaw.sh)
registra entrambi gli MCP, abilita gli hook di notifica del gateway, prova
un invio di test e stampa le righe da aggiungere alla configurazione di
Limen per il canale webhook, insieme all'URL della Agent Card. Guida
completa e troubleshooting:
[docs/openclaw.md](https://github.com/agent-engineering-studio/limen/blob/main/docs/openclaw.md).

## Sicurezza e garanzie

- **Nessuna integrazione cambia un punteggio.** API, tile, strumenti di
  lettura e skill A2A leggono quello che il motore ha già scritto.
- **Le azioni di scrittura sono fail-closed.** Richiedono `MCP_ADMIN_TOKEN`;
  se la variabile non è impostata, sono spente.
- **Nessun modello linguistico negli avvisi.** I testi delle notifiche sono
  deterministici; l'AI scrive solo i racconti, che sono segnalati come tali.
- **Le porte pubblicate dai container si legano al loopback per default.**
  L'esposizione pubblica passa da un reverse proxy su HTTPS; i server MCP
  non vanno esposti senza.
- **Nessun dato personale conservato.** L'unica rotta che riceve dati da un
  visitatore, quella dei contributi, li inoltra per email e non li salva.
