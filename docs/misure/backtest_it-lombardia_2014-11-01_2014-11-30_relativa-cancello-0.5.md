# Limen backtest report — AOI `it-lombardia` — V1

Window: **2014-11-01T00:00:00+00:00 → 2014-11-30T23:00:00+00:00**
Generated: 2026-11-25T13:40:04.660678+00:00

- Cells scored per hour: **24694**
- Configurazione: verità ogni precisione; sorgenti IR, NR; pioggia modello; antecedenti regione (riferimento nazionale); sismica spenta; cancello d'innesco: senza innesco > 0.5 il punteggio non supera 0.34; innesco cumulata 24 h / q0.999 del nodo (sostituisce, saturazione 1.0)
- Truth events (in window): **27**
- Alert-level cell-hours: **1283115**
- Hits: **27**, false alarms: **20315**, misses: **0**

## §2.5 metrics

- **Hit rate**: 100.00% (non è un gate, vedi #243)
- **Colte a parità di carico**: 3.70% (1) con il 5.00% di celle in allerta (punteggio ≥ 0.6823) — il confronto fra varianti
- **FAR**: 99.87% (non è un gate a 1 km², vedi #122)
- **Discriminazione**: 1.21 (hit rate su 82.38% di celle in allerta) (target ≥ 2.0) — **FAIL**
- **Mean lead time**: 79.4 h (target ≥ 18 h) — **PASS**

## Per comune (il metro dell'epica #345)

- Comuni con un evento: **23**
- **Colti ≥ Moderato entro 72 h**: 100.00% (23) con il 17.40% di comuni-giorno ≥ Moderato
- **Colti con il 10% di comuni-giorno in allerta**: 100.00% (23), punteggio ≥ 0.4808, carico effettivo 10.00% (target ≥ 90%) — **FAIL**

## Provenienza

| | |
|---|---|
| generato | 2026-11-25T13:40:04+00:00 |
| commit | `1fcb98c4f9212391f15c770d242ce5b2e0f2d404` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest` |
| `LIMEN_BACKTEST_AOI` | `it-lombardia` |
| `LIMEN_BACKTEST_CANCELLO_INNESCO` | `0.5:0.34` |
| `LIMEN_BACKTEST_CLIMA` | `<percorso locale>` |
| `LIMEN_BACKTEST_END` | `2014-11-30T23:00:00+00:00` |
| `LIMEN_BACKTEST_HIGH_LEVEL` | `Moderate` |
| `LIMEN_BACKTEST_SORGENTI` | `IR,NR` |
| `LIMEN_BACKTEST_START` | `2014-11-01T00:00:00+00:00` |
| `LIMEN_REPORTS_DIR` | `<percorso locale>` |
