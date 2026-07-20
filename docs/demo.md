# Demo locale su un AOI piccolo

Percorso minimo per provare Limen **senza scaricare o processare l'intero
dataset nazionale** (20 regioni, ~312k celle). Semini solo le AOI pilota
(Puglia + Basilicata), scori poche celle di **una** regione e leggi il
risultato dall'API. Utile per testare scoring, risposte API e mappa senza
attese lunghe.

> ⚠️ Limen è uno strumento di **supporto alle decisioni**: gli output sono
> indicatori modellati, **non allerte ufficiali** di Protezione Civile.

## Prerequisiti

- Docker + Docker Compose
- [`uv`](https://github.com/astral-sh/uv)
- `uv sync --all-groups` (una volta)

## Passi (in ordine)

```bash
# 1. Database di sviluppo (Postgres 16 + PostGIS). Leggero, nessun dato esterno.
make up-dev

# 2. Migrazioni + seed delle sole AOI pilota (Puglia + Basilicata) + griglia 1 km.
#    NON scarica il catalogo nazionale né e-ITALICA.
make seed

# 3. Un ciclo di scoring su UNA regione, poche celle (veloce).
LIMEN_MONITOR_AOI=it-basilicata LIMEN_MONITOR_CELL_LIMIT=25 uv run limen monitor-once

# 4. Avvia l'API e leggi il risultato.
uv run limen serve            # http://localhost:8080/docs
curl -s http://localhost:8080/api/aoi/it-basilicata/risk/latest | jq
```

## Output atteso

- **Passo 3** logga il workflow MAF (`AreaResolver → … → PersistResult`) e
  termina con le celle valutate, es. `cells_scored=25`.
- **Passo 4** restituisce l'ultima valutazione persistita per la regione — una
  lista di celle con `score` (0–1) e `level` (`None`…`VeryHigh`) + il briefing
  in italiano. La forma completa è in [`docs/api.md`](./api.md).

Con il solo `make seed` i **fattori statici** per cella (`cell_static_factors`)
sono vuoti: la componente `S` sarà bassa e il rischio dominato dal meteo. È
atteso per la demo — il sistema **degrada** senza sollevare errori.

## Passi opzionali (segnati perché più pesanti)

| Passo | Cosa aggiunge | Costo |
|---|---|---|
| `make bootstrap-static` | densità IFFI + PAI + slope per cella (componente `S` realistica) | richiede il PostGIS di GeoServer popolato |
| `make calibrate` | statistiche di normalizzazione per-AOI + `s_static` | dipende da bootstrap-static |
| `make init` | **intero territorio nazionale** (20 regioni) + download **e-ITALICA** da Zenodo + bootstrap + calibrate | ⏳ **grande**: download esterni e minuti di elaborazione |
| `( cd frontend && npm ci && npm run dev )` | mappa interattiva su `:5173` | build npm |

Per il percorso completo e la modalità produzione vedi il [README](../README.md)
e il [runbook](./runbook.md).
