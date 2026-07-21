# Design — Aggregazione del rischio per comune (e regione)

> Data: 2026-07-21 · Stato: approvato in brainstorming, pre-plan.
> Driver: **A** (chiarezza operatore) + **C** (nuovo dato analitico per
> comune/regione), **B** (performance) come bonus.

## 1. Obiettivo e contesto

Con la copertura nazionale (20 regioni, ~312k celle da 1 km²) l'operatore di
protezione civile si perde negli elenchi lunghi di celle. Introduciamo un
**rollup amministrativo per comune** — la regione è già coperta da
`v_region_tiles` (migration 019), che implementa la stessa semantica
"classe della peggior cella + conteggi".

Il rischio-comune è definito così (deciso in brainstorming):

- **Headline = classe della peggior cella** del comune (prudenziale, difendibile
  per un ente pubblico: "se anche 1 km² è Alto, il comune mostra Alto"). Riusa
  la classe per-cella — nessun cutoff nuovo.
- **Profilo sempre visibile**: n° celle per classe, punteggio max, celle esposte.
- **Classifica comuni ordinata per esposizione** (Σ del componente E sulle celle
  High+): una zona abitata sale in cima, ma la *classe* resta "peggior cella".

Non introduciamo la soglia-di-copertura (opzione scartata), né alert-per-comune,
né clustering spaziale nuovo (il DBSCAN del report resta invariato).

## 2. Fondamenta dati (lavoro nuovo principale)

I confini ISTAT dei comuni (`com01012023_g`) vivono nel **DB GeoServer separato**
(`GEOSERVER_SOURCE__DB_DSN`), non nell'operativo; le celle non sono taggate per
comune. Portiamo entrambe le cose nell'operativo (niente query cross-DB nel
percorso caldo — coerente con il vincolo self-hosted/no-cloud).

- **Tabella `comuni`** (operativo): `istat_code` (PK), `name`, `aoi_id`,
  `geom` MULTIPOLYGON(4326), `centroid` POINT(4326).
  Seed one-shot dal DB GeoServer, filtrato alle AOI seminate (default: tutte le
  regioni seminate ≈ copertura nazionale). Nuovo comando idempotente
  `limen seed-comuni`.
- **Tabella `cell_comune`**: `cell_id` (PK) → `istat_code`. Mapping statico via
  join spaziale (`ST_Contains(comune.geom, cell.centroid)`), idempotente,
  ri-eseguibile solo quando griglia o confini cambiano (raro). Popolata da
  `limen seed-comuni` dopo il caricamento di `comuni`.

Migrazione SQL nuova (`NNN_comuni.sql`): crea `comuni` + `cell_comune` +
`mv_comune_risk` (sotto). Immutabile una volta applicata.

## 3. Modello di aggregazione

**`mv_comune_risk`** — materialized view, specchio di `v_region_tiles` a livello
comune:

| colonna | significato |
|---|---|
| `istat_code`, `name`, `aoi_id` | identità del comune |
| `worst_class` | classe della cella peggiore (headline) |
| `max_score` | punteggio massimo |
| `n_cells` | celle totali nel comune |
| `n_none … n_veryhigh` | conteggi per classe (profilo) |
| `n_alert` | celle High+ (badge sulla mappa) |
| `exposure_rank` | Σ del componente E sulle celle High+ (ordinamento classifica) |
| `geom`, `centroid` | poligono comune + centroide (tiles + badge/drill-down) |

Query: `mv_latest_risk ⨝ cell_comune ⨝ comuni`, `GROUP BY istat_code`. La classe
peggiore usa lo stesso pattern di `v_region_tiles`
(`array_agg(risk_level ORDER BY risk_score DESC)[1]`).

Il componente **E** (esposizione) per il ranking viene esposto in
`mv_latest_risk` (o letto dai `factors` persistiti) — dettaglio da fissare nel
piano; se non immediato, l'`exposure_rank` degrada a `n_alert` e la classifica
resta ordinata per (worst_class, n_alert, max_score).

**Refresh**: estendiamo `refresh_mv_latest_risk()` perché, in coda, rinfreschi
anche `mv_comune_risk` (dipende dal latest per-cella). Così tutti i chiamati
esistenti — in primis `PersistResult` — aggiornano il comune senza modifiche.
Invariante "mai `REFRESH MATERIALIZED VIEW` diretto" rispettato.

**Regione**: nessun lavoro nuovo — `v_region_tiles` è già il rollup regione.

## 4. Superfici

- **Mappa** (MapLibre + pg_tileserv): tier `regione (0–10) → comune (~7–11) →
  cella (5–14)`. `mv_comune_risk` servita come nuovo layer pg_tileserv;
  choropleth per `worst_class` (palette YlOrRd), **badge conteggio `n_alert`
  solo sui comuni High+**, clic su comune → drill-down (fly-to + apertura celle).
- **Sidebar** (`RegionAccordion`, grouping-per-comune della Fase 1): il summary
  del comune mostra l'**headline** (classe peggiore) + celle esposte, oltre al
  min/max già presente.
- **Classifica comuni**: nuovo pannello (o sezione della sidebar), comuni
  ordinati per `exposure_rank`, con classe peggiore + `n_alert`.
- **REST API** (nessuna logica negli endpoint — solo lettura della view):
  - `GET /api/comuni?aoi=&limit=` → classifica.
  - `GET /api/comune/{istat_code}` → dettaglio + celle del comune.
- **MCP / A2A** (sola lettura, riusano la view):
  - `tool_comune_risk(istat_code)` + `tool_top_comuni(limit?, aoi_id?)`.
  - Skill A2A equivalenti (`comune_risk`, `top_comuni`).
- **Report statico**: nuova sezione "comuni a maggior rischio" (tabella:
  comune, classe peggiore, celle in allerta, esposti), accanto ai cluster
  spaziali DBSCAN già presenti. Nessun LLM.
- **Alert**: **solo arricchimento** del payload/summary col nome del comune.
  Resta un alert **per-cella** con dedup — nessun nuovo alert-per-comune, per
  non toccare gli invarianti del percorso allerta.

## 5. Invarianti e configurazione

- Soglie parametriche (cutoff badge = livello alert; eventuali future) in
  `regional_thresholds.yaml`, validate dallo schema Pydantic. Nessuna costante
  hard-coded nel codice di aggregazione.
- Aggregazione **pura e deterministica**, niente rete/LLM nel percorso.
- No cloud: confini comuni importati nell'operativo; il DB GeoServer è usato solo
  al momento del `seed-comuni` (offline), mai nel percorso caldo.
- Idempotenza: `seed-comuni` ri-eseguibile in sicurezza.

## 6. Testing

- **Unit**: rollup SQL con fixture (celle→comune→classe/conteggi/esposizione);
  ranking per esposizione (puro); tool MCP/A2A + endpoint REST (TestClient, no
  DB); sezione report (render puro).
- **Live** (Postgres reale): `seed-comuni` (comuni + cell_comune) →
  `mv_comune_risk` popolata → refresh via pipeline → API/tool restituiscono la
  classifica.

## 7. Fuori scope (YAGNI)

- Alert-per-comune (resta per-cella).
- Soglia-di-copertura per la classe (resta "peggior cella").
- Nuovo clustering spaziale (il DBSCAN del report è invariato).
- Livelli amministrativi oltre comune + regione (niente province).

## 8. Componenti e confini

| Unità | Cosa fa | Dipende da |
|---|---|---|
| `comuni` + `cell_comune` + `seed-comuni` | porta confini ISTAT e tagga le celle nell'operativo | DB GeoServer (solo al seed), grid_cells |
| `mv_comune_risk` + refresh esteso | rollup deterministico per comune | `mv_latest_risk`, `cell_comune`, `comuni` |
| tile layer comune (pg_tileserv) | choropleth + badge sulla mappa | `mv_comune_risk` |
| REST `/api/comuni*` | classifica + dettaglio per la SPA | `mv_comune_risk` |
| tool MCP/A2A comune | interrogazione agentica | `mv_comune_risk` |
| sezione report + arricchimento alert | vista amministrativa + contesto comune | `mv_comune_risk`, `comuni` |
