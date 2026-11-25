# Limen backtest report — AOI `it-campania` — V1

Window: **2009-01-01T00:00:00+00:00 → 2009-01-31T23:00:00+00:00**
Generated: 2026-11-24T23:08:24.801510+00:00

- Cells scored per hour: **14161**
- Configurazione: verità ogni precisione; sorgenti IR, NR; pioggia modello; antecedenti regione (riferimento nazionale); sismica spenta
- Truth events (in window): **29**
- Alert-level cell-hours: **6455141**
- Hits: **26**, false alarms: **9331**, misses: **3**

## §2.5 metrics

- **Hit rate**: 89.66% (non è un gate, vedi #243)
- **Colte a parità di carico**: 10.34% (3) con il 5.00% di celle in allerta (punteggio ≥ 0.4861) — il confronto fra varianti
- **FAR**: 99.72% (non è un gate a 1 km², vedi #122)
- **Discriminazione**: 1.36 (hit rate su 66.08% di celle in allerta) (target ≥ 2.0) — **FAIL**
- **Mean lead time**: 101.5 h (target ≥ 18 h) — **PASS**

## Per comune (il metro dell'epica #345)

- Comuni con un evento: **21**
- **Colti ≥ Moderato entro 72 h**: 100.00% (21) con il 83.54% di comuni-giorno ≥ Moderato
- **Colti con il 10% di comuni-giorno in allerta**: 66.67% (14), punteggio ≥ 0.4717, carico effettivo 10.00% (target ≥ 90%) — **FAIL**

## Provenienza

| | |
|---|---|
| generato | 2026-11-24T23:08:24+00:00 |
| commit | `5ed0fe4d0f758d55da88ca7f0f10dc1747637e14` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest` |
| `LIMEN_BACKTEST_AOI` | `it-campania` |
| `LIMEN_BACKTEST_CLIMA` | `<percorso locale>` |
| `LIMEN_BACKTEST_END` | `2009-01-31T23:00:00+00:00` |
| `LIMEN_BACKTEST_HIGH_LEVEL` | `Moderate` |
| `LIMEN_BACKTEST_SORGENTI` | `IR,NR` |
| `LIMEN_BACKTEST_START` | `2009-01-01T00:00:00+00:00` |
| `LIMEN_BACKUP_DIR` | `<percorso locale>` |
| `LIMEN_DATA_ROOT` | `<percorso locale>` |
| `LIMEN_DOMINIO` | `localhost` |
| `LIMEN_IMAGE_PREFIX` | `ghcr.io/agent-engineering-studio/limen-` |
| `LIMEN_IMAGE_TAG` | `sha-c1e3ded` |
| `LIMEN_IMPERVIOUSNESS_RASTER` | `<percorso locale>` |
| `LIMEN_PROXY_BIND` | `127.0.0.1` |
| `LIMEN_REPORTS_DIR` | `<percorso locale>` |
