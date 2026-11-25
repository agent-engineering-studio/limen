# Limen backtest report — AOI `it-lombardia` — V1

Window: **2014-11-01T00:00:00+00:00 → 2014-11-30T23:00:00+00:00**
Generated: 2026-11-25T00:27:08.725237+00:00

- Cells scored per hour: **24694**
- Configurazione: verità ogni precisione; sorgenti IR, NR; pioggia modello; antecedenti regione (riferimento nazionale); sismica spenta
- Truth events (in window): **27**
- Alert-level cell-hours: **7780450**
- Hits: **26**, false alarms: **11371**, misses: **1**

## §2.5 metrics

- **Hit rate**: 96.30% (non è un gate, vedi #243)
- **Colte a parità di carico**: 3.70% (1) con il 5.00% di celle in allerta (punteggio ≥ 0.5956) — il confronto fra varianti
- **FAR**: 99.77% (non è un gate a 1 km², vedi #122)
- **Discriminazione**: 2.09 (hit rate su 46.15% di celle in allerta) (target ≥ 2.0) — **PASS**
- **Mean lead time**: 118.9 h (target ≥ 18 h) — **PASS**

## Per comune (il metro dell'epica #345)

- Comuni con un evento: **23**
- **Colti ≥ Moderato entro 72 h**: 100.00% (23) con il 42.19% di comuni-giorno ≥ Moderato
- **Colti con il 10% di comuni-giorno in allerta**: 73.91% (17), punteggio ≥ 0.5266, carico effettivo 10.00% (target ≥ 90%) — **FAIL**

## Provenienza

| | |
|---|---|
| generato | 2026-11-25T00:27:08+00:00 |
| commit | `5ed0fe4d0f758d55da88ca7f0f10dc1747637e14` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest` |
| `LIMEN_BACKTEST_AOI` | `it-lombardia` |
| `LIMEN_BACKTEST_CLIMA` | `<percorso locale>` |
| `LIMEN_BACKTEST_END` | `2014-11-30T23:00:00+00:00` |
| `LIMEN_BACKTEST_HIGH_LEVEL` | `Moderate` |
| `LIMEN_BACKTEST_SORGENTI` | `IR,NR` |
| `LIMEN_BACKTEST_START` | `2014-11-01T00:00:00+00:00` |
| `LIMEN_BACKUP_DIR` | `<percorso locale>` |
| `LIMEN_DATA_ROOT` | `<percorso locale>` |
| `LIMEN_DOMINIO` | `localhost` |
| `LIMEN_IMAGE_PREFIX` | `ghcr.io/agent-engineering-studio/limen-` |
| `LIMEN_IMAGE_TAG` | `sha-c1e3ded` |
| `LIMEN_IMPERVIOUSNESS_RASTER` | `<percorso locale>` |
| `LIMEN_PROXY_BIND` | `127.0.0.1` |
| `LIMEN_REPORTS_DIR` | `<percorso locale>` |
