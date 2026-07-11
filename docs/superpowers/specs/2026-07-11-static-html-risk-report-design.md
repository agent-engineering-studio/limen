# Report HTML statico delle zone a rischio — design

> Data: 2026-07-11 · Stato: **spec approvanda**
> Comando nuovo: `limen report build` + job APScheduler `limen-html-report`.

## 1. Obiettivo

Produrre un **report HTML statico**, ben formattato e autosufficiente, che
elenca le **zone a maggior rischio frana** con la porzione di mappa interessata
e il **motivo dettagliato**. Doppio uso, stesso motore di generazione:

- **Demo / vetrina** su GitHub Pages (estetica, storytelling, mappe belle).
- **Deliverable operativo** consultabile periodicamente.

Generazione **automatica**: un report all'avvio dell'applicazione, poi **ogni
ora** (allineato a `hourly_monitoring`), con idempotenza che evita ricostruzioni
inutili quando i dati non cambiano.

**Ogni generazione conserva le versioni precedenti** (archivio immutabile). Lo
scopo è duplice: (1) fact-checking a posteriori — confrontare cosa il report
prevedeva al tempo T con gli eventi realmente accaduti dopo; (2) arricchire la
base dati per le versioni future del modello. La chiave di questo design: **le
previsioni storiche e gli eventi reali sono già nel DB** (`risk_assessments`
append-only + `landslide_events`/`iffi_landslides`), quindi il report NON
duplica le previsioni — conserva i propri snapshot HTML + un `manifest.json`
per build, e la verifica vera è un job separato che riusa lo storico DB.

## 2. Vincoli e riuso (cosa NON si costruisce)

Il progetto ha già tutto tranne il rendering HTML e lo snapshot mappa.

| Serve | Riuso esistente |
|---|---|
| Dati AOI (celle, distribuzione, `briefing_it`, `analysis`) | `AggregateAssessment` persistito (`core/models/context.py`) |
| Quadro nazionale + nomi luogo | `national_report()` (`mcp/tools.py`) → `regions`, `totals`, `top_cells`, `report_it` |
| Geometria + score + fattori per cella | vista materializzata `mv_latest_risk` (geom, risk_score, risk_level, factors jsonb) |
| Palette / classi / label IT | `frontend/src/lib/risk-colors.ts` → `RISK_CLASSES` (5 hex YlOrRd, range, label) |
| Testo motivo (deterministico) | logica `plainSummary`/`verdict` di `CellPopup.tsx` + `_format_summary_it` (`notifications/base.py`) |
| Scheduling in-process | `register_jobs` (`api/jobs/registration.py`) + lifespan (`api/main.py`) |
| Skeleton job report | `api/jobs/daily_report.py` (`run_daily_report`) |

Vincoli invarianti rispettati: APScheduler (no pg_cron), no cloud SDK, no ORM,
degradazione neutra sui fetch esterni, `structlog` (no `print`), idempotenza CLI.

## 3. Architettura

Nuovo package `src/limen/report/`:

```
src/limen/report/
├── builder.py       # orchestratore: dati → cluster → snapshot → HTML → (push)
├── clustering.py    # query PostGIS ST_ClusterDBSCAN → cluster di celle contigue
├── snapshot.py      # bbox cluster → basemap raster + overlay celle → PNG
├── reasons.py       # motivo deterministico da factors (port di plainSummary/verdict)
├── palette.py       # mirror di RISK_CLASSES (hex, label IT, range) server-side
├── render.py        # Jinja2 → index.html
└── templates/
    └── report.html.j2   # CSS inline, self-contained
```

Job: `api/jobs/html_report.py` (`run_html_report`) registrato in `register_jobs`.

Flusso `builder.build()`:
1. Per ogni AOI: carica l'ultimo `AggregateAssessment` (con `briefing_it`,
   `analysis`).
2. **Idempotenza**: SHA-256 su canonical-JSON degli assessment usati. Se il
   build più recente in archivio ha la stessa firma, **salta** l'intero build
   (niente dir nuova, niente PNG, niente push) e logga `report.skip`. Un build
   avviene solo quando i dati sono effettivamente cambiati → l'archivio cresce
   solo con contenuto nuovo.
3. Clustering (§4) → lista di cluster `High+`.
4. Cap `html_max_clusters` per score decrescente; logga quanti cluster omessi.
5. Per ogni cluster: snapshot PNG (§5) + motivo (§6).
6. **Output versionato immutabile** (§8): scrive in
   `report/archive/<valuation_time>/` → `index.html` + `assets/*.png` +
   `manifest.json`. Aggiorna il puntatore `report/index.html` (redirect
   all'ultimo) senza toccare le versioni passate.
7. (Opzionale) pubblicazione su GitHub Pages (§8).

## 4. Clustering (unico pezzo algoritmico — è SQL)

Celle contigue `High`/`VeryHigh` raggruppate via `ST_ClusterDBSCAN` come window
function su `mv_latest_risk`. Nessuna libreria di clustering Python.

```sql
SELECT ST_ClusterDBSCAN(centroid, eps := :grid_step * 1.5, minpoints := 1)
         OVER ()                        AS cluster_id,
       cell_id, aoi_id, risk_score, risk_level, factors,
       ST_AsGeoJSON(geom)               AS geom_json,
       ST_X(centroid) AS lon, ST_Y(centroid) AS lat
FROM   mv_latest_risk
WHERE  risk_level IN ('High', 'VeryHigh')
```

Raggruppamento in Python per `cluster_id` → per cluster: bbox (union delle celle),
`max_score`, cella dominante (score massimo), driver prevalente. `eps` deriva dal
passo griglia (~1 km) così celle adiacenti finiscono nello stesso cluster.

## 5. Snapshot PNG (Pillow + `_http`)

Per ogni cluster:
1. bbox del cluster + margine → livello di zoom slippy-map.
2. Scarico i tile raster necessari (OSM/Carto) via `integrations._http`
   (client condiviso + retry). **Cache su disco** per `{z}/{x}/{y}` (TTL lungo):
   niente ri-download, rispetto della ToS.
3. Compongo i tile nel canvas, riproietto i poligoni cella (EPSG:4326 → pixel Web
   Mercator) e li disegno semi-trasparenti con gli hex di `RISK_CLASSES`, +
   contorno AOI come contesto.
4. Attribuzione "© OpenStreetMap contributors" impressa nel PNG.
5. Output `report/assets/cluster-{id}.png`.

**Degradazione**: se il fetch tile fallisce, fallback a snapshot SVG puro (solo
poligoni + contorno) — il report esce comunque, non solleva.

## 6. Motivo dettagliato (riuso, nessuna invenzione)

Per ogni cluster:
- Narrativa AOI: `briefing_it` **già persistito** (LLM). Il report NON richiama
  l'LLM a build-time (invariante "alerts never invent figures" esteso: il testo è
  quello già calcolato dal monitoraggio).
- `analysis.driver` + `analysis.anomalies` + `analysis.confidence` dell'AOI.
- Spiegazione deterministica per cluster costruita dai `factors` della cella
  dominante: contributi S/M/E/F/H/K resi come barre HTML/CSS (port di
  `plainSummary`/`verdict` in `reasons.py`).

## 7. Rendering HTML

- **Jinja2** (già installato 3.1.6; dichiarato come dip diretta in `pyproject`),
  autoescape attivo. Template `report.html.j2` con **CSS inline** → un solo file
  `index.html` autosufficiente + cartella `assets/`.
- Palette/label da `report/palette.py` (mirror di `RISK_CLASSES`).
- Legenda 5-classi ColorBrewer YlOrRd con label IT + range (WCAG-AA, mai
  solo-colore — invariante palette).
- Struttura pagina: header (data valutazione, versione pipeline) → quadro
  nazionale (`national_report`) → sezioni cluster ordinate per score, ognuna con
  snapshot, distribuzione livelli, motivo, barre componenti.

## 8. Timing e pubblicazione

**Timing** — job nuovo, a intervallo, gemello di `forecast_monitoring`:

```python
JOB_HTML_REPORT = "limen-html-report"

if deps.settings.report.html_enabled:
    await scheduler.add_schedule(
        run_html_report, args=(deps,),
        trigger=IntervalTrigger(hours=cfg.html_interval_hours),  # default 1
        id=JOB_HTML_REPORT,
        conflict_policy=ConflictPolicy.replace,
        max_running_jobs=1,          # anti-overlap
    )
```

Run al boot — kickoff fire-and-forget nel lifespan (`api/main.py`, dopo
`scheduler.start_in_background()`), che non blocca né rompe lo startup:

```python
if deps.settings.report.html_run_at_startup:
    asyncio.create_task(_safe(run_html_report, deps))
```

Risultato: **1 report all'avvio + 1 ogni ora**, disaccoppiato dal monitoraggio;
l'idempotenza (§3.2) rende sostenibile la cadenza oraria saltando i rebuild a
dati invariati.

**Archivio immutabile** — layout output:

```
report/
├── index.html                       # redirect all'ultimo build (unico file mutabile)
├── archive/
│   ├── 2026-07-11T0800Z/
│   │   ├── index.html               # snapshot immutabile
│   │   ├── assets/cluster-*.png
│   │   └── manifest.json            # cosa ha asserito QUESTO report
│   └── 2026-07-11T0900Z/ …
└── archive/index.json               # indice dei build (timeline navigabile)
```

`manifest.json` per build: `valuation_time`, `pipeline_version`,
`assessment_sha256`, e la lista cluster (`cluster_id`, `cell_ids`, `max_score`,
`level`, `driver`, bbox). È la registrazione machine-readable di cosa il report
ha *asserito* — substrato del fact-checking, senza ri-derivare i cluster e senza
duplicare il raw assessment (che resta in `risk_assessments`).

**Retention** — i `manifest.json` sono minuscoli e si conservano
indefinitamente (sono il dataset per il fact-checking). HTML+PNG delle versioni
vecchie si potano oltre `html_archive_keep` build (default generoso); i manifest
restano. L'idempotenza (§3.2) limita già la crescita ai soli build con dati nuovi.

**Pubblicazione GitHub Pages** — il VPS che possiede il DB esegue il build e fa
push su un branch orfano `gh-pages`. L'archivio è **append**: ogni build aggiunge
una dir sotto `archive/` e aggiorna solo `index.html` + `archive/index.json`; le
versioni passate non vengono mai riscritte. GitHub Actions non può girare il
generatore (DB self-hosted). Push gated da `report.html_publish` (default
`false`); di default il job produce solo la cartella locale.

## 8b. Consumatore: verifica previsione×evento (progettato, fuori scope ora)

Il fact-checking è un **job separato**, non parte del build del report. A
orizzonte scaduto (es. 24-72h dopo un `valuation_time`), interroga lo storico:
prende le previsioni `High+` da `risk_assessments` (o dai `manifest.json`
archiviati) per la finestra, le joina spazialmente con `landslide_events` /
`iffi_landslides` occorsi *dopo* la previsione, e produce etichette hit / miss /
false-alarm + metriche §2.5 (hit rate, FAR, lead time). È `limen backtest`
applicato in avanti sullo stream live; riusa la stessa logica. Il suo output
etichettato è ciò che "arricchisce la base dati" per calibrazione/ML futuri.
Questa spec lo *abilita* (archivio + manifest immutabili) ma non lo implementa.

## 9. Settings nuovi (`ReportSettings`, env `REPORT__…`)

```python
html_enabled: bool = True
html_interval_hours: int = Field(default=1, ge=1)   # REPORT__HTML_INTERVAL_HOURS
html_run_at_startup: bool = True
html_output_dir: Path = Path("report")
html_max_clusters: int = Field(default=50, ge=1)
html_min_level: RiskLevel = RiskLevel.High
html_archive_keep: int = Field(default=240, ge=1)    # HTML/PNG mantenuti; manifest sempre
html_publish: bool = False                           # push su gh-pages
```

## 10. Fuori scope (YAGNI)

- Export PDF (basta la stampa browser del PNG statico).
- Mappa interattiva nel report (scelto rendering statico).
- Nuovo endpoint API (lettura DB diretta via repo + `mv_latest_risk`).
- Algoritmo di clustering custom (PostGIS `ST_ClusterDBSCAN`).
- Richiamo LLM a build-time (si riusa `briefing_it` già persistito).
- Store parallelo delle previsioni (già in `risk_assessments` append-only).
- Job di verifica previsione×evento e tabella outcome (§8b): abilitato ma non
  implementato qui — è `backtest` in avanti, feature successiva.

## 11. Test (minimi, non framework-heavy)

- `clustering`: fixture di celle a griglia → verifica che celle adiacenti
  finiscano nello stesso cluster e celle isolate no.
- `reasons`: dato un `factors` con driver noto → stringa/barre attese.
- `render`: assessment fittizio → `index.html` non vuoto, contiene le classi e i
  path PNG attesi, HTML ben formato.
- `snapshot`: proiezione 4326→pixel su bbox noto → coordinate attese; fallback SVG
  quando il fetch tile è mockato in errore.
- idempotenza: due build consecutivi a dati invariati → il secondo logga
  `report.skip` e non crea una nuova dir in `archive/`.
- archivio: un build con dati nuovi crea `archive/<valuation_time>/` con
  `manifest.json` valido (cluster + cell_ids + hash) e NON tocca le dir
  precedenti (immutabilità); `index.html` punta all'ultimo.
