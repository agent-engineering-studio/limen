# Fonti → sezioni

Cosa leggere per ogni sezione, in ordine di autorità (il primo vince). Le
date dei documenti le dà `scripts/inventario.py`: un documento più vecchio
del codice che descrive va verificato riga per riga.

## «Come funziona» — `docs/guida/limen.md`

Le `##` attuali sono la struttura di riferimento: si arricchiscono, non si
rimescolano (gli indirizzi `#/come-funziona/<slug>` sono linkati da mappa,
legenda, home e popup).

| Sezione (`##`) | Codice / config (autorità) | Documenti |
|---|---|---|
| Cosa aggiunge al bollettino · In breve | `CLAUDE.md` (intestazione, invarianti) | `docs/divulgazione/01-*`, `README.md` § intro |
| Come leggere la mappa | `frontend/src/lib/risk-colors.ts`, `LegendPanel.tsx`, `NationalStrip.tsx`, `ComuniBoard.tsx` | `CLAUDE.md` «Risk palette», «Non misurato» |
| Il territorio in celle | `src/limen/data/seed/`, migrazioni `grid_cells`/`comuni`, `mv_comune_risk` | `docs/data-model.md`, `docs/architecture.md` § Copertura |
| Il layer dati: gli open data | `src/limen/integrations/*`, `integrations/static_bootstrap/`, `limen data-status` | `docs/divulgazione/04-fonti-dati-open.md`, `README.md` § Componenti e sorgenti / Attribuzione, `docs/geodata.md` |
| I tre motori | `src/limen/config/hazards/{landslide,flood,wildfire,cascades}.yaml`, `src/limen/core/scoring/`, `core/scoring/wildfire/fwi.py` | `docs/scoring-model.md`, `docs/warning-logic.md`, `docs/divulgazione/02-*`, `CLAUDE.md` «Flood», «Wildfire», «FWI chain» |
| La previsione | `src/limen/api/jobs/`, `agents/workflows/`, `SCHEDULER__*` in `config/settings.py` | `CLAUDE.md` «Three cadences», `docs/runbook.md` § Ciclo di una giornata |
| Il layer machine learning | `src/limen/ml/`, `agents/executors/shadow_challenger.py` | `docs/ml.md`, `docs/divulgazione/03-*`, `docs/iot.md` (sensori in-situ) |
| Il layer AI | `agents/chat_agents/` (+ `prompts/*.it.md`), `agents/llm_factory/`, `src/limen/knowledge/` | `docs/inference.md`, `docs/grounding.md`, `docs/divulgazione/05-*`, `CLAUDE.md` «LLM is non-authoritative», «quality-local» |
| Leggere i dati per prevedere un disastro | `frontend/src/content/verifiche/*.json` (casi verificati) | `docs/artifacts/backtest_oct_2018.md`, `docs/warning-logic.md` |
| Limiti dichiarati | `CLAUDE.md` § Phase boundary | `docs/warning-logic.md` § 8, `docs/divulgazione/03-*` § Cosa manca |
| La tecnologia | `docker-compose*.yml`, `infra/`, `pyproject.toml`, `frontend/package.json` | `docs/architecture.md`, `docs/deployment.md`, `docs/divulgazione/06-*`, `README.md` § Perché queste scelte |
| Glossario | — | `docs/divulgazione/glossario.md` |

Sezioni che oggi mancano e meritano una `##` propria quando la skill gira
in modalità «molto dettagliata» (aggiungile **dopo** quelle esistenti dello
stesso livello, per non spostare le ancore):

- **L'architettura** (dopo «La previsione» o dentro «La tecnologia»): api
  e `worker` separati e perché, tre cadenze, pipeline delle tile
  (`mv_latest_risk` → `risk_at`/`forecast_at` → pg_tileserv → MapLibre),
  partizioni e retention, degrado neutro e flag `measured`. Fonti:
  `docs/architecture.md` (vecchio: verifica), `CLAUDE.md`.
- **Le cascate fra pericoli**: `cascades.yaml` (fuoco → alluvione,
  pioggia congiunta, indice di attenzione per comune).
- **Come si verifica**: backtest §2.5 (hit rate + tasso di base + FAR +
  anticipo), shadow ML, la pagina Verifiche e il suo riquadro
  «Inefficienza». Fonti: `docs/scoring-model.md` §2.5, `docs/ml.md`,
  `limen backtest*` in `src/limen/cli/`.

Non vanno nella guida: `docs/HANDOFF.md` (operativo, interno),
`docs/demo.md` e `docs/runbook.md` oltre ai fatti di cadenza,
`docs/superpowers/` (piani di lavoro), `docs/OSS_IMPACT.md` (posizionamento).

## «Integrazioni» — `docs/guida/integrazioni.md`

Pagina per sviluppatori e agenti. Qui i nomi tecnici sono il contenuto.

| Sezione (`##`) proposta | Codice (autorità) | Documenti |
|---|---|---|
| Panoramica: cinque modi di leggere Limen | — | `docs/architecture.md` |
| API REST | `src/limen/api/endpoints/*.py`, `api/schemas.py`, `/openapi.json` | `docs/api.md` (vecchio: mancano comuni, regioni, provenienza, spiegazione, storico, shadow, status) |
| Tile vettoriali | `api/endpoints/tiles.py`, migrazioni di `risk_at`, `forecast_at`, `v_risk_tiles`, `v_region_tiles`, `mv_comune_risk` | `CLAUDE.md` «Views pin the default hazard», «Tile pipeline» |
| MCP — `limen-ops`, `ispra-geo` | `src/limen/mcp/server.py`, `mcp/tools.py`, `geodata/src/geodata/mcp/server.py` | `docs/openclaw.md`, `docs/geodata.md` |
| A2A | `src/limen/a2a/{card,skills,service,store}.py`, `api/endpoints/a2a.py` | `docs/openclaw.md` § A2A |
| Notifiche push | `src/limen/notifications/` (telegram, mqtt, email, webhook, dispatcher, governance) | `docs/openclaw.md` § wake/agent, `CLAUDE.md` «Notifications», «Dedup» |
| Dati aperti in uscita e licenze | `api/endpoints/regioni.py` (`rapporto.pdf`), `report/regioni_pdf.py`, `frontend/src/lib/attribuzioni.ts` | `README.md` § Attribuzione & licenze open, `CLAUDE.md` «Copernicus attribution» |
| Setup rapido (OpenClaw) | `scripts/setup_openclaw.sh` | `docs/openclaw.md` |
| Sicurezza e garanzie | `MCP_ADMIN_TOKEN` fail-closed, porte su loopback, sola lettura sul punteggio | `CLAUDE.md` «MCP refresh is admin-only», «Published ports bind to loopback» |

Per ogni rotta REST: metodo e percorso, parametri (con default e valori
ammessi di `hazard`), cosa restituisce (i campi che contano, non lo schema
intero), un esempio `curl` corto, e il caso degradato (cosa risponde
quando una fonte manca: `None`/`[]`, mai un 500). Raggruppa per uso
(territorio, rischio per cella, comuni e regioni, previsione e allerte,
spiegazioni e provenienza, diagnostica, salute), non per file.
