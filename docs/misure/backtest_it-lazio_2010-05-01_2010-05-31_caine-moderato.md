# Limen backtest report — AOI `it-lazio` — V1

Window: **2010-05-01T00:00:00+00:00 → 2010-05-31T23:00:00+00:00**
Generated: 2026-11-24T22:46:51.362409+00:00

- Cells scored per hour: **17862**
- Configurazione: verità ogni precisione; sorgenti IR, NR; pioggia modello; antecedenti regione (riferimento nazionale); sismica spenta
- Truth events (in window): **23**
- Alert-level cell-hours: **2929262**
- Hits: **10**, false alarms: **5376**, misses: **13**

## §2.5 metrics

- **Hit rate**: 43.48% (non è un gate, vedi #243)
- **Colte a parità di carico**: 0.00% (0) con il 5.00% di celle in allerta (punteggio ≥ 0.4701) — il confronto fra varianti
- **FAR**: 99.81% (non è un gate a 1 km², vedi #122)
- **Discriminazione**: 1.44 (hit rate su 30.15% di celle in allerta) (target ≥ 2.0) — **FAIL**
- **Mean lead time**: 120.0 h (target ≥ 18 h) — **PASS**

## Per comune (il metro dell'epica #345)

- Comuni con un evento: **19**
- **Colti ≥ Moderato entro 72 h**: 100.00% (19) con il 77.85% di comuni-giorno ≥ Moderato
- **Colti con il 10% di comuni-giorno in allerta**: 10.53% (2), punteggio ≥ 0.4585, carico effettivo 10.00% (target ≥ 90%) — **FAIL**

## Provenienza

| | |
|---|---|
| generato | 2026-11-24T22:46:51+00:00 |
| commit | `5ed0fe4d0f758d55da88ca7f0f10dc1747637e14` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest` |
| `LIMEN_BACKTEST_AOI` | `it-lazio` |
| `LIMEN_BACKTEST_CLIMA` | `<percorso locale>` |
| `LIMEN_BACKTEST_END` | `2010-05-31T23:00:00+00:00` |
| `LIMEN_BACKTEST_HIGH_LEVEL` | `Moderate` |
| `LIMEN_BACKTEST_SORGENTI` | `IR,NR` |
| `LIMEN_BACKTEST_START` | `2010-05-01T00:00:00+00:00` |
| `LIMEN_BACKUP_DIR` | `<percorso locale>` |
| `LIMEN_DATA_ROOT` | `<percorso locale>` |
| `LIMEN_DOMINIO` | `localhost` |
| `LIMEN_IMAGE_PREFIX` | `ghcr.io/agent-engineering-studio/limen-` |
| `LIMEN_IMAGE_TAG` | `sha-c1e3ded` |
| `LIMEN_IMPERVIOUSNESS_RASTER` | `<percorso locale>` |
| `LIMEN_PROXY_BIND` | `127.0.0.1` |
| `LIMEN_REPORTS_DIR` | `<percorso locale>` |
