# Limen backtest report — AOI `it-campania` — V1

Window: **2009-01-01T00:00:00+00:00 → 2009-01-31T23:00:00+00:00**
Generated: 2026-11-25T12:06:24.730409+00:00

- Cells scored per hour: **14161**
- Configurazione: verità ogni precisione; sorgenti IR, NR; pioggia modello; antecedenti regione (riferimento nazionale); sismica spenta; cancello d'innesco: senza innesco > 0.5 il punteggio non supera 0.34; innesco cumulata 24 h / q0.999 del nodo (sostituisce, saturazione 1.0)
- Truth events (in window): **29**
- Alert-level cell-hours: **677017**
- Hits: **23**, false alarms: **11902**, misses: **6**

## §2.5 metrics

- **Hit rate**: 79.31% (non è un gate, vedi #243)
- **Colte a parità di carico**: 0.00% (0) con il 5.00% di celle in allerta (punteggio ≥ 0.5966) — il confronto fra varianti
- **FAR**: 99.81% (non è un gate a 1 km², vedi #122)
- **Discriminazione**: 0.94 (hit rate su 84.21% di celle in allerta) (target ≥ 2.0) — **FAIL**
- **Mean lead time**: 48.8 h (target ≥ 18 h) — **PASS**

## Per comune (il metro dell'epica #345)

- Comuni con un evento: **21**
- **Colti ≥ Moderato entro 72 h**: 80.95% (17) con il 16.59% di comuni-giorno ≥ Moderato
- **Colti con il 10% di comuni-giorno in allerta**: 71.43% (15), punteggio ≥ 0.5407, carico effettivo 10.00% (target ≥ 90%) — **FAIL**

## Provenienza

| | |
|---|---|
| generato | 2026-11-25T12:06:24+00:00 |
| commit | `1fcb98c4f9212391f15c770d242ce5b2e0f2d404` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest` |
| `LIMEN_BACKTEST_AOI` | `it-campania` |
| `LIMEN_BACKTEST_CANCELLO_INNESCO` | `0.5:0.34` |
| `LIMEN_BACKTEST_CLIMA` | `<percorso locale>` |
| `LIMEN_BACKTEST_END` | `2009-01-31T23:00:00+00:00` |
| `LIMEN_BACKTEST_HIGH_LEVEL` | `Moderate` |
| `LIMEN_BACKTEST_SORGENTI` | `IR,NR` |
| `LIMEN_BACKTEST_START` | `2009-01-01T00:00:00+00:00` |
| `LIMEN_REPORTS_DIR` | `<percorso locale>` |
