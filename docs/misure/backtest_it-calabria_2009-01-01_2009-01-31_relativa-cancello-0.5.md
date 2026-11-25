# Limen backtest report — AOI `it-calabria` — V1

Window: **2009-01-01T00:00:00+00:00 → 2009-01-31T23:00:00+00:00**
Generated: 2026-11-25T12:40:38.906453+00:00

- Cells scored per hour: **15601**
- Configurazione: verità ogni precisione; sorgenti IR, NR; pioggia modello; antecedenti regione (riferimento nazionale); sismica spenta; cancello d'innesco: senza innesco > 0.5 il punteggio non supera 0.34; innesco cumulata 24 h / q0.999 del nodo (sostituisce, saturazione 1.0)
- Truth events (in window): **32**
- Alert-level cell-hours: **564731**
- Hits: **30**, false alarms: **14546**, misses: **2**

## §2.5 metrics

- **Hit rate**: 93.75% (non è un gate, vedi #243)
- **Colte a parità di carico**: 31.25% (10) con il 5.00% di celle in allerta (punteggio ≥ 0.6438) — il confronto fra varianti
- **FAR**: 99.79% (non è un gate a 1 km², vedi #122)
- **Discriminazione**: 1.00 (hit rate su 93.43% di celle in allerta) (target ≥ 2.0) — **FAIL**
- **Mean lead time**: 73.2 h (target ≥ 18 h) — **PASS**

## Per comune (il metro dell'epica #345)

- Comuni con un evento: **21**
- **Colti ≥ Moderato entro 72 h**: 95.24% (20) con il 13.71% di comuni-giorno ≥ Moderato
- **Colti con il 10% di comuni-giorno in allerta**: 95.24% (20), punteggio ≥ 0.5669, carico effettivo 10.00% (target ≥ 90%) — **FAIL**

## Provenienza

| | |
|---|---|
| generato | 2026-11-25T12:40:38+00:00 |
| commit | `1fcb98c4f9212391f15c770d242ce5b2e0f2d404` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest` |
| `LIMEN_BACKTEST_AOI` | `it-calabria` |
| `LIMEN_BACKTEST_CANCELLO_INNESCO` | `0.5:0.34` |
| `LIMEN_BACKTEST_CLIMA` | `<percorso locale>` |
| `LIMEN_BACKTEST_END` | `2009-01-31T23:00:00+00:00` |
| `LIMEN_BACKTEST_HIGH_LEVEL` | `Moderate` |
| `LIMEN_BACKTEST_SORGENTI` | `IR,NR` |
| `LIMEN_BACKTEST_START` | `2009-01-01T00:00:00+00:00` |
| `LIMEN_REPORTS_DIR` | `<percorso locale>` |
