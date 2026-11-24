# Limen backtest report — AOI `it-trentino-alto-adige` — V1

Window: **2014-11-01T00:00:00+00:00 → 2014-11-30T23:00:00+00:00**
Generated: 2026-11-24T12:53:03.113033+00:00

- Cells scored per hour: **14078**
- Configurazione: verità ogni precisione; sorgenti IR, NR; pioggia pluviometri; antecedenti regione (riferimento nazionale); sismica spenta
- Truth events (in window): **6**
- Alert-level cell-hours: **35441**
- Hits: **1**, false alarms: **1241**, misses: **5**

## §2.5 metrics

- **Hit rate**: 16.67% (non è un gate, vedi #243)
- **Colte a parità di carico**: 0.00% (0) con il 5.00% di celle in allerta (punteggio ≥ 0.5653) — il confronto fra varianti
- **FAR**: 99.92% (non è un gate a 1 km², vedi #122)
- **Discriminazione**: 1.89 (hit rate su 8.82% di celle in allerta) (target ≥ 2.0) — **FAIL**
- **Mean lead time**: 102.0 h (target ≥ 18 h) — **PASS**

## Per comune (il metro dell'epica #345)

- Comuni con un evento: **5**
- **Colti ≥ Moderato entro 72 h**: 100.00% (5) con il 95.58% di comuni-giorno ≥ Moderato
- **Colti con il 10% di comuni-giorno in allerta**: 80.00% (4), punteggio ≥ 0.5143, carico effettivo 10.00% (target ≥ 90%) — **FAIL**

## Provenienza

| | |
|---|---|
| generato | 2026-11-24T12:53:03+00:00 |
| commit | `4ac5bf4bebf2ce15abcb4fe37bc791a4a6845ecf` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest` |
| `LIMEN_BACKTEST_AOI` | `it-trentino-alto-adige` |
| `LIMEN_BACKTEST_END` | `2014-11-30T23:00:00+00:00` |
| `LIMEN_BACKTEST_PIOGGIA` | `pluviometri` |
| `LIMEN_BACKTEST_SORGENTI` | `IR,NR` |
| `LIMEN_BACKTEST_START` | `2014-11-01T00:00:00+00:00` |
| `LIMEN_BACKUP_DIR` | `<percorso locale>` |
| `LIMEN_DATA_ROOT` | `<percorso locale>` |
| `LIMEN_DOMINIO` | `localhost` |
| `LIMEN_IMAGE_PREFIX` | `ghcr.io/agent-engineering-studio/limen-` |
| `LIMEN_IMAGE_TAG` | `sha-fa4dccd` |
| `LIMEN_IMPERVIOUSNESS_RASTER` | `<percorso locale>` |
| `LIMEN_PROXY_BIND` | `127.0.0.1` |
| `LIMEN_REPORTS_DIR` | `<percorso locale>` |
