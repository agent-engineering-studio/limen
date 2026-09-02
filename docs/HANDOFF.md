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
- Backlog storico in `docs/HANDOFF.md` §4 e nelle issue GitHub (`gh issue list`).

---

## 3. Comandi essenziali (da `CLAUDE.md`)

```bash
make install                 # uv sync --all-groups
make up-dev                  # Postgres 16 + PostGIS + pg_cron + pgvector
make seed                    # migrazioni + AOI Puglia/Basilicata + griglia 1 km
make migrate                 # solo migrazioni pendenti
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
`regional_thresholds.yaml`; HTTP esterno via `integrations/_http`; degradazione
neutra in lettura; V1 deterministico resta il champion; refresh matview **solo**
via `refresh_mv_latest_risk()`; alert mai inventati + dedup obbligatorio; geodata
mai nel critical path. Leggerli prima di lavorare.
