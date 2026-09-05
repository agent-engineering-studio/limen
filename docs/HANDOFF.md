# Handoff — passaggio al server dedicato (2026-07-22)

> Documento di continuità per le sessioni di **Claude Code sul nuovo server**.
> Le *memorie* di Claude sono locali alla macchina (`~/.claude/projects/.../memory/`)
> e **non si trasferiscono** con la repo: tutto ciò che serve ricordare è
> ricopiato qui. Leggi anche `CLAUDE.md` (invarianti di progetto) e `README.md`.

---

## 0. La prima cosa da fare sul nuovo server

1. **Correggere i path assoluti in `.env`** (oggi puntano al Mac dell'autore):
   ```
   LIMEN_DEM_RASTER=/Users/gzileni/Git/mcp-geoserver/data/HRDTM5m.tif
   LIMEN_CORINE_RASTER=/Users/gzileni/Git/mcp-geoserver/data/clc2018_it/clc2018_it_100m.tif
   LIMEN_GEOLOGICAL_SHAPEFILE=/Users/gzileni/Git/mcp-geoserver/data/carta_geolitologica/carta_geolitologica.shp
   ```
   Ripuntarli alla posizione dei dataset sul nuovo host (o lasciarli vuoti: gli
   slot mancanti degradano e il bootstrap logga `static_bootstrap.skip`).
   Anche `GEOSERVER_SOURCE__DB_DSN` va aggiornato all'host del DB GeoServer.
2. **Docker su Linux x86**: usare l'immagine PostGIS ufficiale `postgis/postgis:16-3.5`
   (su Apple Silicon serviva `imresamu/postgis-arm64` via `LIMEN_TEST_POSTGIS_IMAGE`
   / `POSTGIS_BASE`; sul server dedicato x86 non serve l'override).
   > Gli errori I/O di Docker visti in locale erano **disco pieno**, non bug —
   > sul server con più spazio dovrebbero sparire.
3. **Storage: Postgres è su dischi meccanici, l'NVMe è inutilizzato** (misurato
   il 2026-09-02 sul server dedicato). `/var/lib/docker` è su
   `vg1-lv_docker`, stripe LVM di tre HDD (Toshiba DT01ACA2, WD15EADS,
   ST2000DM001); i due NVMe (Samsung 512 G, Crucial P3 500 G) ospitano solo
   `/`, `/srv/models` e un `/srv/wal` da 32 G evidentemente predisposto per il
   WAL e mai collegato. `pg_test_fsync`, host scarico:

   | Percorso | Device | `fdatasync` |
   |---|---|---|
   | `/` | NVMe | 884 ops/s (1.1 ms) |
   | `/var/lib/docker` (dati Postgres) | stripe HDD | 76 ops/s (13 ms) |
   | `/srv/appdata` (repo) | stripe HDD | **0.69 ops/s (1.45 s)** |

   Conseguenze concrete: `initdb` esegue migliaia di fsync singoli e sull'HDD
   **non completa** entro la wait strategy dei testcontainers (verificato: con
   `POSTGRES_INITDB_ARGS=--no-sync` lo stesso container è pronto in 10 s; con
   fsync attivo resta bloccato oltre 3 minuti a 0% CPU). Per questo il datadir
   dei test è su **tmpfs** in `tests/conftest.py`: il cluster è usa-e-getta,
   la durabilità non serve.

   Per il DB operativo la leva è `LIMEN_PGDATA_DIR` (compose dev/demo): puntalo
   a una directory su NVMe. La migrazione richiede fermo servizio —
   `docker compose stop postgres`, copia di `limen-pgdata/_data` sulla nuova
   path, riavvio — quindi va pianificata, non fatta di corsa.

   ⚠️ **La causa a monte è `sdb` (WDC WD15EADS-11P, seriale WD-WMAVU1961972):
   un disco moribondo.** `iostat -dx`, due campioni a sistema quasi scarico:

   | Disco | `w_await` | `f_await` (flush) | `%util` a ~5 write/s |
   |---|---|---|---|
   | sda (Toshiba) | 3.6 ms | 4.1 ms | 1% |
   | **sdb (WD Green)** | **453 → 2248 ms** | **607 → 978 ms** | **100%** |
   | sdc (Seagate) | 7.9 ms | 7.7 ms | 2% |

   Tutti gli LV di `vg1` sono in stripe sui tre dischi, quindi **ogni** fsync
   su `/var/lib/docker` e `/srv/appdata` attende `sdb`: da qui l'`initdb` che
   non finisce, i seed lentissimi e l'fsync da 1.45 s. Non è un problema di
   configurazione Docker né di kernel.

   Ordine di intervento consigliato:
   1. `LIMEN_PGDATA_DIR` su un percorso in `vg0` (NVMe) — sposta il DB fuori
      dallo stripe malato senza toccare i dischi.
   2. Sostituire `sdb`, o evacuarlo con `pvmove /dev/sdb` e `vgreduce` se c'è
      spazio libero sugli altri PV.
   3. `apt install smartmontools && smartctl -a /dev/sdb` per la conferma
      formale (SMART non è installato sull'host).
4. **Bring-up**: `make up-dev` → `make seed` (o `make migrate`) → `uv run limen seed-comuni`
   (serve `GEOSERVER_SOURCE__DB_DSN`) → `uv run limen create-admin` (env
   `LIMEN_ADMIN_EMAIL`/`_PASSWORD`).

---

## 1. Stato del progetto (tutto su `main`, branch puliti locale+remoto)

Versione: implementazione completa, in fase di test. Feature mergiate di recente:

- **Fase 1 hazard-agnostic COMPLETA** (2026-09-05, epic #57, PR #88 #89 #91 #92
  #93 + questa). L'architettura è multi-rischio nella struttura e mono-rischio
  nei dati: `hazard_type` attraversa tabelle, viste, API, MCP e A2A, ma
  l'unico pericolo configurato è `landslide`. Aggiungerne uno è **uno YAML in
  `config/hazards/` più una registrazione nel registry**, senza toccare
  workflow, API o persistenza — è il criterio di accettazione dell'epic, e un
  test lo dimostra registrando un motore fittizio.
  Cosa sapere prima di abilitarne un secondo:
  1. serve `config/hazards/<hazard>.yaml` **completo**: #84 ha rifiutato di
     proposito un file di blocchi condivisi, perché soglie di classe e
     mappatura di allerta sono per-pericolo nella sostanza;
  2. vanno rivisti i **sei oggetti dipendenti** da `mv_latest_risk`
     (migrazioni 016, 018, 019, 020, 023, 026), tutti fissati su `landslide`
     perché con un solo pericolo nulla si rompe a runtime e un errore
     resterebbe invisibile fino alla Fase 2;
  3. `mv_comune_risk` e il report nazionale restano mono-rischio: il loro
     `exposure_rank` legge una chiave che solo il breakdown delle frane ha
     (#58, Fase 4). API e tool MCP **rifiutano** un pericolo diverso lì,
     invece di restituire numeri delle frane sotto un'altra etichetta;
  4. gli step condivisi del workflow girano una volta per *(pericolo, AOI)*,
     non una per AOI: con due pericoli i fetch meteo e GloFAS raddoppiano.
     Condividerli richiede di spezzare la pipeline in prefisso territoriale e
     code per pericolo. Documentato nella docstring di
     `build_hazard_workflow`, non fatto a metà.

- **Fase 1a multi-hazard + partizionamento** (2026-09-04, issue #82, epic #57;
  assorbe #79) — migrazioni `028_multi_hazard_partitioned.sql` e
  `029_risk_at_stable_order.sql`. `hazard_type` su `risk_assessments`,
  `model_runs`, `norm_stats`, `training_samples`, `alert_dispatches`,
  `forecast_dispatches`; tabella di lookup `hazards` (solo `landslide`
  abilitato). `mv_latest_risk` ha ora una riga per *(cella, hazard abilitato)*
  e le sei viste/funzioni a valle sono fissate su `landslide`, quindi i numeri
  della mappa pubblica non cambiano. `risk_assessments` e `model_runs` sono
  partizionate per giorno su `computed_at`: la retention elimina partizioni.
  **Tre difetti pre-esistenti corretti nello stesso passaggio** (dettaglio in
  §2). Verificato sui dati reali del server: 3 418 556 righe conservate,
  `mv_latest_risk` identica byte per byte, `v_region_tiles` identica,
  migrazione applicata in 1 min 53 s.

- **Gateway di inferenza self-hosted** (2026-09-03, `ee83f2f`) — tutto il
  traffico LLM passa dal gateway LiteLLM su `:8091`; mai llama-swap (`:8083`) o
  colibrì (`:8070`) diretti. `LLM__MODELS__*` ora funziona sui motori locali
  (dietro il gateway i nomi dei modelli sono chiavi di routing arbitrarie), ma
  onora **solo i ruoli dichiarati** in environment: i default del codice sono id
  Claude che il gateway rifiuterebbe con 400. Timeout 600→120 s + override
  per-ruolo. Nuovo `limen llm-check`. Evento unico `llm.fallback` quando un ruolo
  ripiega sul deterministico. **`quality-local`/`glm52` vietati sui percorsi
  sincroni con rifiuto all'avvio** (vedi §5). Tutte le porte pubblicate su
  `127.0.0.1`. Doc: `docs/inference.md`.
  Repo collegati: `mcp-geo-server` `7ad6189` (provider `openai`),
  `aes-inference-lab` `ec9824a` (alias `glm52`).
- **`make build` copre tutto lo stack** (2026-09-03, `19fa2ca`) — costruiva 3
  immagini su 4 di quelle di Limen: `limen/geodata:0.1`, cioè `geodata-init`
  **e** `ispra-geo-mcp`, non veniva mai vista perché `COMPOSE_ALL` include solo
  demo + geoserver. Ora spazza demo + geoserver + geodata + observability in due
  passi (build per le proprie, `pull --ignore-buildable` per terze parti e
  cross-repo): 15 servizi, 4 immagini costruite, 8 scaricate. `COMPOSE_BUILD` è
  separato da `COMPOSE_ALL` di proposito — `make build` deve *vedere* geodata,
  `make up` non deve *avviarlo*.
  Attenzione: `make build-images` resta un target distinto e non ridondante —
  costruisce con `--platform linux/amd64` esplicito (la base `postgis/postgis`
  non ha manifest arm64) e produce anche `frontend/dist/`.
- **Auth su database** (issue #49, PR #50-53) — **Clerk rimosso** (non ammesso per la
  PA). `src/limen/auth/`: password scrypt (stdlib), verifica email via codice
  (SMTP riusato dal canale email; in dev il codice va nei log), sessioni
  server-side in cookie httpOnly (`sessions`), ruoli `admin`/`ml-ops`/`operatore`/
  `viewer`. Endpoint `/api/auth/*`, admin dashboard `/api/admin/*` + UI `#/admin`,
  CLI `limen create-admin`. **SPID = seam OIDC fail-closed** (`SPID__*` non
  configurato ⇒ disattivo): da cablare a un proxy/aggregatore **accreditato AgID**
  quando disponibile. Frontend: `AuthProvider`/`useAuth`, pagine `#/accedi`,
  `#/registrati`, `#/verifica`. CORS: `allow_credentials=True` + origini esplicite
  (`API__CORS_ORIGINS`; default Vite dev). `AUTH__ENABLED=false` di default ⇒
  endpoint protetti aperti finché non lo attivi.
- **A2A (Agent2Agent) + OpenClaw** (issue #3, PR #48) — Agent Card
  `/.well-known/agent-card.json` + endpoint JSON-RPC `/a2a` (message/send,
  message/stream SSE, tasks/get|cancel, push), task in `a2a_tasks`. Tool MCP
  admin `tool_build_report`/`tool_forecast_history` (fail-closed su
  `MCP_ADMIN_TOKEN`). `scripts/setup_openclaw.sh` registra `limen-ops` + `ispra-geo`.
  Pagina UI **Integrazioni** (`#/integrazioni`). Guida: `docs/openclaw.md`.
- **Aggregazione per comune** (PR #54) — `mv_comune_risk` (specchio di
  `v_region_tiles`): classe della peggior cella + profilo + classifica per
  esposizione. `comuni` + `cell_comune` popolati da `limen seed-comuni`; refresh
  agganciato a `refresh_mv_latest_risk()`. Superfici: mappa (choropleth comune
  zoom 7–11 + badge celle-in-allerta solo High+ + drill-down), sidebar +
  classifica comuni, REST `/api/comuni` + `/api/comune/{istat}`, tool MCP/A2A
  `top_comuni`/`comune_risk`, sezione report, comune negli alert. Migrazione
  `026_comuni.sql`. Spec+piano in `docs/superpowers/`.
- **Flood forecast** (issue #8) — componente H dinamico multi-sorgente
  (OpenMeteo Flood/GloFAS + Marine + pericolosità ISPRA); `ENABLE_FLOOD_FORECAST`
  **ON di default**. Progetto riposizionato come rischio **frane + inondazioni**
  (fiumi/laghi/mare) in UI/README/docs.
- **Trend forecast** — `limen forecast-history` persiste il trend +24/48/72h in
  `risk_assessments` (horizon `+Hh`); sparkline in sidebar + grafico nel report
  statico. Popolato per tutte le 20 AOI il 2026-07-21.

**Ultima migrazione applicata: `026_comuni.sql`.** Le migrazioni sono immutabili
una volta applicate (checksum SHA-256) — mai editarle, aggiungerne di nuove.

---

## 2. Lavoro in sospeso / da riprendere

### Difetti pre-esistenti corretti in #82 (da tenere a mente)

1. **La retention di `risk_assessments` non era mai girata.**
   `_purge_old_assessments` in `api/jobs/cache_cleanup.py` era definita ma
   nessuno la chiamava, quindi la tabella che cresce di ~15 GB/giorno non
   veniva mai potata. Ora entrambe le tabelle calde passano da
   `drop_expired_partitions()` dentro `run_cache_cleanup_job`.
2. **Il debounce del refresh era inerte dalla migrazione 026.** La 017 aveva
   introdotto la finestra di 5 minuti su `mv_refresh_state`; la 026 ha
   ridefinito `refresh_mv_latest_risk()` per agganciare il rollup comunale
   copiando il corpo dalla 007 e perdendo il debounce. Da allora *ogni*
   chiamata di PersistResult rifaceva un refresh completo di 312k righe più
   quello comunale, venti volte per sweep nazionale. Il debounce è
   ripristinato; i test che si aspettano un refresh immediato azzerano
   `mv_refresh_state` (il fixture `reset_db` lo fa da solo).
3. **`DB__COMMAND_TIMEOUT_SECONDS` (30 s) uccideva le migrazioni lunghe.**
   Nessuna migrazione lo aveva mai superato finché la 028 non ha dovuto
   copiare 3,4 milioni di righe: la transazione veniva annullata a metà e
   sembrava una migrazione rotta. `data/migrate.py` ora applica ogni file con
   `_APPLY_TIMEOUT_SECONDS = 1800`.

### Da sapere sulle partizioni

- Le partizioni giornaliere vanno create **prima** che uno sweep scriva. Le
  crea il job `limen-partitions` (registrato **sempre**, ogni
  `SCHEDULER__PARTITIONS_INTERVAL_HOURS`, default 6), più un tentativo
  best-effort all'avvio dell'API e `uv run limen partitions` a mano. Non
  rimetterle dentro il job di cache-cleanup: quello **non viene registrato**
  con `SCHEDULER__CACHE_CLEANUP=pg_cron`, e la retention resterebbe ferma.
  Righe in `risk_assessments_default` sono un difetto, non uno stato normale:
  la retention non le raggiunge. Il log `partitions.default_not_empty` le
  segnala.
- Quando #77 sposterà lo scheduler nel processo `worker`, il gancio
  best-effort che oggi sta nel lifespan dell'API va portato lì: il primo tick
  del job è differito di `SCHEDULER__PARTITIONS_INTERVAL_HOURS`, quindi senza
  il gancio all'avvio le partizioni nascerebbero solo dopo 6 ore.
- I confini delle partizioni sono in **UTC** (`now() AT TIME ZONE 'UTC'`), non
  nel TimeZone della sessione: altrimenti su un server non-UTC il giorno a cui
  una riga appartiene e il giorno che dà il nome alla partizione divergono.
- `refresh_mv_latest_risk()` restituisce il timbro del debounce in caso di
  errore, così un fallimento transitorio non silenzia i retry per 5 minuti.
  `limen seed-comuni` chiama `refresh_mv_comune_risk()` **diretto**: passare
  dalla catena con debounce rendeva la prima popolazione un no-op silenzioso.
- `risk_at()` ordina le feature per `cell_id` (migrazione 029): senza
  quell'ordine i byte del tile dipendevano dall'ordine fisico delle righe,
  quindi cambiavano dopo un `VACUUM FULL` o una ricostruzione della tabella a
  contenuto identico, rendendo inutile qualsiasi ETag.

### Da fare adesso — gateway di inferenza (2026-09-03)

Il codice è su `main` in tutti i repo coinvolti. **Due azioni restano fuori
dalla portata di una sessione Claude** (servono root / accesso al server), più
una che dipende da un altro repo.

1. **[BLOCCANTE, serve `sudo`] Rendere `glm52` sul gateway in esecuzione.**
   `setup/etc/litellm/config.yaml` in `aes-inference-lab` è il *template*:
   `/etc/litellm/config.yaml` viene generato da lì con `envsubst`
   (`setup/scripts/40-install-services.sh:122`). Finché non lo rendi, il gateway
   continua ad annunciare 6 modelli e `glm52` non esiste per nessun client.
   ```bash
   cd /srv/appdata/git/aes-inference-lab && git checkout main && git pull
   sudo bash setup/scripts/40-install-services.sh   # riavvia solo le unit cambiate
   curl -s http://127.0.0.1:8091/v1/models \
     | python3 -c 'import sys,json; print([m["id"] for m in json.load(sys.stdin)["data"]])'
   ```
   Lo script riavvia solo le unit il cui file è cambiato, quindi colibrì e i suoi
   ~10 GB **non** vengono ricaricati.

2. **[BLOCCANTE] Applicare limen sul server e verificare dal container.**
   Il cambio di `ports:` richiede `up -d`, non `restart`.
   ⚠️ **Le porte ora sono su `127.0.0.1`.** Se raggiungi API o frontend da
   un'altra macchina senza reverse proxy, servono `LIMEN_API_BIND=0.0.0.0` /
   `LIMEN_FRONTEND_BIND=0.0.0.0` in `.env` **prima** di ricreare i container,
   altrimenti il servizio sparisce dalla rete e sembra un guasto.
   ```bash
   git checkout main && git pull
   printf 'LLM__LLAMACPP_BASE_URL=http://127.0.0.1:8091\nAPI_LLM_LLAMACPP_BASE_URL=http://host.docker.internal:8091\n' >> .env
   docker compose -f infra/docker/docker-compose.demo.yml up -d --build api
   docker compose -f infra/docker/docker-compose.demo.yml exec api limen llm-check
   ss -tlnp | grep -E '5432|1883|7800|8080'   # atteso 127.0.0.1, non 0.0.0.0
   ```
   `llm-check` va eseguito **dentro** il container: da host `127.0.0.1` funziona
   e dal container no, quindi una verifica da host non prova niente.

3. **[FATTO — resta solo `up -d`] Immagini GeoServer.** Pubblicate su GHCR il
   2026-09-03 (run `33781145378`, `:latest` 16:54 + `:bootstrap` 17:06,
   multi-arch, CI verde: **93 passed, 2 skipped**). Verificato **dentro
   l'immagine pubblicata** che `GEO_LLM_PROVIDER=openai` costruisca un
   `OpenAIChatClient`, non solo nel sorgente. `make build` le scarica già, quindi
   sul server basta `up -d`.
   Nota: sono **due tag distinti** — `geoserver-mcp` usa `:latest`,
   `geoserver-webui` e `geoserver-init` usano `:bootstrap`. Ricostruirne uno solo
   lascia metà dello stack sul codice vecchio senza un errore evidente.

4. **[BLOCCATO da un altro repo] Grounding KG.** Applicata l'**opzione B**: il
   sidecar non è più un servizio dei compose di Limen (`74a69de`) — quell'entry
   non era mai stata avviabile (immagine `knowledge-graph:latest` inesistente,
   `neo4j`/`redis` non definiti, `host.docker.internal` senza `extra_hosts`).
   Lo stack KG gira dal suo repo; Limen punta solo `KG__BASE_URL`:
   ```bash
   # nel repo knowledge-graph
   docker compose -f docker-compose.ghcr.yml up -d
   # in limen/.env
   KG__ENABLED=true
   API_KG_BASE_URL=http://host.docker.internal:8000
   ```
   ⚠️ **Non funzionerà finché knowledge-graph#7 non è risolta.** Catena
   verificata: la CI di quel repo è rossa (`ruff` non pinnato, `requirements.txt`
   dichiara `ruff>=0.4.0` e la CI risolve alla 0.16.1 → 21 rilievi su codice
   preesistente), `docker-publish` è **gated sulla CI** via `workflow_run`,
   quindi è `skipped` e **`kg-api:latest` è ancora costruita da `eab6c0b`
   (11 giugno)**. Il provider llama.cpp/OpenAI è su `main` (PR #5) ma non
   nell'immagine: chi la usa ottiene il comportamento pre-#5, solo Ollama, senza
   alcun segnale. Issue aperte: **#7** (blocco CI, con i 21 rilievi elencati) e
   **#6** (provider `openai` di prima classe — il `llamacpp_provider` parla già
   OpenAI su `/v1`, manca solo che si chiami come ciò che fa).

5. **Ruolo asincrono per colibrì — progettato, non implementato.** Un modello che
   genera in decine di minuti è un modello *batch*: serve un ruolo dedicato
   (`report`/`deep_analysis`) fuori da `LLM__MODELS__*` con allowlist propria, un
   job asincrono che lo invoca, ed esito **persistito** con stato
   `pending`/`done`/`failed` letto da un endpoint che risponde subito. Design
   completo in `docs/inference.md` §«Come si userà colibrì». Finché non esiste,
   colibrì è inutilizzabile da Limen **per costruzione** — ed è il comportamento
   voluto.
6. **Mode-change fantasma nei repo affiancati.** `mcp-geo-server` (47 file) e
   `knowledge-graph` (182 file) hanno file passati da `100644` a `100755` —
   artefatto della migrazione, 0 righe di differenza. Sporcano `git status` e
   hanno già bloccato due `git switch`. Fanno anche scattare `EXE002` in ruff
   locale (eseguibile senza shebang), gonfiando il conteggio errori rispetto
   alla CI: 69 invece di 21. Rimedio: `git config core.fileMode false` in quei
   repo. Non applicato: è una scelta sulle copie di lavoro locali.

### Trappole in cui sono già caduto (leggere prima di indagare)

- **`git fetch` fallisce in silenzio se il remote è SSH.** In questa sessione
  `origin` di `limen` e `mcp-geo-server` è `git@github.com:` e la chiave non è
  caricata nella shell, quindi `git fetch origin` esce con errore e i ref
  `origin/*` restano **vecchi**. Mi ha portato a leggere `git show main:file` su
  un `main` di tre mesi prima e a dichiarare assente una feature che c'era.
  Sempre `git -c credential.helper='!gh auth git-credential' fetch https://...`
  e verificare la sha prima di concludere qualcosa su un altro branch.
- **`pkill -f "<pattern>"` uccide la propria shell** quando il pattern compare
  nella command line del `bash -c` che lo contiene. Ha ammazzato tre run di
  test/mypy lasciando processi orfani che scrivevano sullo stesso file di
  output, con risultati incoerenti. Usare i PID.
- **Un file di output vuoto non è un pass.** Un `mypy` troncato da `timeout`
  esce 124 e non scrive niente: identico a "nessun errore". Controllare sempre
  il codice di uscita, non la dimensione del file.

### Backlog precedente

- **Pulizia disco (dataset statici)** — sul Mac occupavano ~93 GB, rigenerabili e
  non versionati (solo `data/README.md` è in git). Sul nuovo server con più spazio
  è meno urgente, ma per riferimento:
  - `mcp-geoserver/data-processed/hrdtm5m.tif` (40G, DEM processato, rigenerabile
    dal grezzo; montato RO nei container GeoServer).
  - `mcp-geoserver/data/HRDTM5m.tif` (21G grezzo, referenziato da `.env`).
  - `limen/data/` (inventory 2.6G, osm 2.3G, hazard 1.9G; il DEM duplicato
    `limen/data/dem` è già stato cancellato il 2026-07-21).
  - Nessuno è nel percorso operativo caldo (invariante "geodata mai nel critical
    path"): l'API legge feature pre-calcolate dal DB. Servono solo per ri-ingest.
- **Validazioni live rimaste** (bloccate in locale dal Docker instabile, da rifare
  sul server): smoke browser del login auth (Vite `npm run dev` + API), curl
  `/api/comuni` con `serve`, integration test `tests/integration/test_alert_dispatch_executor.py`
  (era rosso solo per errore I/O di testcontainers, non per il codice).
- **SPID reale**: richiede accreditamento AgID + proxy SPID/CIE OIDC, poi impostare
  `SPID__*`. Il seam è pronto.
- **Verdetto shadow ML** (issue #4): finestra di osservazione ~fino a inizio agosto
  2026 prima che la retention 30gg mangi i dati; il challenger ML era
  sistematicamente più basso del champion → probabile "non promuovere".
- **Coastal flood signal**: `coastal_surge_norm` è None per centroidi interni
  (Marine API senza onde); follow-up = campionare un punto costiero.
- **Issue GitHub — 10 aperte, nessuna implementata** (audit del 2026-09-03,
  verificato per grep sul codice, non per titolo; #65 FIRMS chiusa perché
  completa). L'ordine è vincolato dalle dipendenze: **#57** (`hazard_type`,
  registry dei motori, YAML per hazard) sblocca tutto il resto —
  #61→#62→#66→#67/#68 per wildfire, #63→#64 per flood, #58 alla fine. **#59**
  (governance alert: aggregazione comunale, rate limiting, digest) è l'unica che
  può procedere in parallelo, e va chiusa **prima** di abilitare flood in
  produzione. Dettaglio: `gh issue list --repo agent-engineering-studio/limen`.

---

## 3. Comandi essenziali (da `CLAUDE.md`)

```bash
make install                 # uv sync --all-groups
make up-dev                  # Postgres 16 + PostGIS + pg_cron + pgvector
make seed                    # migrazioni + AOI Puglia/Basilicata + griglia 1 km
make migrate                 # solo migrazioni pendenti
uv run limen partitions      # partizioni giornaliere mancanti + stato tabelle calde
uv run limen seed-comuni     # confini ISTAT + tag celle (needs GEOSERVER_SOURCE__DB_DSN)
uv run limen create-admin    # LIMEN_ADMIN_EMAIL / _PASSWORD / _FIRST / _LAST
uv run limen bootstrap-static
uv run limen calibrate
uv run limen monitor-once    # LIMEN_MONITOR_AOI / CELL_LIMIT
uv run limen forecast-history
uv run limen report build
uv run limen serve           # :8080  /docs /health /api/...
uv run limen mcp-serve       # MCP limen-ops (LIMEN_MCP_TRANSPORT=stdio|http)
make check                   # ruff check + mypy --strict + pytest
( cd frontend && npm install && npm run dev )   # SPA su :5173
( cd frontend && npm run lint && npm test && npm run build )
```

**Gate di qualità prima di ogni commit** (obbligatori, CI li verifica):
`uv run ruff check` **+** `uv run ruff format --check` **+** `uv run mypy` **+**
`uv run pytest`; frontend `npm run lint` + `npm test` + `npm run build`.

---

## 4. Contenuto essenziale delle memorie locali (non si trasferiscono col repo)

- **deploy-target**: VPS self-hosted + Docker, **niente cloud** (no AWS/Azure/GCP).
- **object-store-design**: Protocol con backend `filesystem` + `s3`-compatibile
  (MinIO/R2/B2 via `OBJECT_STORE__ENDPOINT_URL`); niente SDK cloud fuori da
  `data/object_store/`. Azure rimosso.
- **production-stack**: Neon ammesso solo dev/test; in prod Postgres containerizzato.
- **auth-strategy**: Clerk **abbandonato** (no PA) → auth su DB (fasi A→D fatte,
  issue #49 chiusa). Vedi §1.
- **llm-local-ollama**: in locale/container preferire **Ollama** host + qwen; il
  resolver salta i provider cloud senza SDK (fix crash hourly_monitoring). Ordine
  resolver: Anthropic → OpenAI → Foundry → Ollama; una chiave cloud vince su
  Ollama salvo `LLM__PROVIDER`.
- **geoserver-mcp-generic**: `geoserver-mcp` è un MCP GeoServer generico/data-agnostic;
  la semantica ISPRA sta solo nel loader Limen. Distinto da `geodata`/`ispra-geo`.
- **data-layout-plan**: `data/` è theme-first country-agnostic (per ruolo nello
  scoring: `dem/`, `hazard/`, `inventory/`…), mai per nazione; tutti i path via env
  var. Un clone = una nazione. Vedi `data/README.md`.
- **testing-cycle-state**: `calibrate` gira (s_static ok); gate S-vs-ISPRA n/a
  (susceptibility vuota); backtest §2.5 storicamente bloccato (IFFI senza date →
  poi ingest ITALICA). Verificare contro lo stato reale del DB.
- **llamafactory-setup**: fine-tuning LLM = ultima spiaggia (gate B3 superato col
  prompt engineering) — non farlo salvo richiesta.

> Sul nuovo server, quando ha senso, si possono ricreare come memorie di Claude
> partendo da questo elenco.

---

## 5. Invarianti da non violare

Sono in `CLAUDE.md` (tabella "Locked invariants"): Python 3.12 + `uv`; asyncpg +
PostGIS, **no ORM**; migrazioni SQL immutabili; geometrie EPSG:4326 (distanze in
3035); scoring engine **puro** (no DB/rete/LLM); costanti solo in
`hazards/landslide.yaml`; HTTP esterno via `integrations/_http`; degradazione
neutra in lettura; V1 deterministico resta il champion; refresh matview **solo**
via `refresh_mv_latest_risk()`; alert mai inventati + dedup obbligatorio; geodata
mai nel critical path. Leggerli prima di lavorare.

Tre aggiunti il 2026-09-03 (dettaglio in `docs/inference.md`):

- **`quality-local`/`glm52` mai su un percorso sincrono.** Misurato: colibrì ha
  risposto 3 token in 40 s (~0,08 tok/s a freddo). *Ogni* ruolo di
  `LLM__MODELS__*` è sincrono — richiesta HTTP, tool MCP, o un tick dello
  scheduler più breve della risposta. Il caso peggiore non è l'HTTP ma la sweep
  oraria: il loop è sequenziale su tutte le AOI e `_sweep_lock` **scarta** i tick
  successivi, quindi un briefing da decine di minuti ferma il monitoraggio
  nazionale senza un solo errore nei log. Imposto da `SLOW_GENERATION_MODELS` +
  `model_validator` su `LLMSettings`: **il processo rifiuta di partire.**
- **Un solo endpoint di inferenza**: il gateway LiteLLM `:8091`. Routing per nome
  modello, tetto di spesa e fallback locale→cloud vivono lì; una porta diretta li
  aggira. `:8081` è **GeoServer**, non un motore LLM. Dai container l'host è
  `host.docker.internal`, mai `127.0.0.1` (che è il container stesso).
- **Porte pubblicate su loopback**: Docker scrive nelle proprie catene iptables
  *prima* di quelle di ufw, quindi il `default deny incoming` dell'host non
  protegge una porta pubblicata. Ogni `ports:` usa una variabile `LIMEN_*_BIND`
  con default `127.0.0.1`; l'esposizione pubblica passa da un reverse proxy su
  443.
