# Limen backtest report — AOI `it-umbria` — V1

Window: **2008-12-01T00:00:00+00:00 → 2008-12-31T23:00:00+00:00**
Generated: 2026-11-25T05:54:18.342694+00:00

- Cells scored per hour: **8828**
- Configurazione: verità ogni precisione; sorgenti IR, NR; pioggia modello; antecedenti regione (riferimento nazionale); sismica spenta; cancello d'innesco: senza innesco > 0.6 il punteggio non supera 0.34; innesco cumulata 24 h / q0.999 del nodo (sostituisce, saturazione 1.0)
- Truth events (in window): **24**
- Alert-level cell-hours: **234476**
- Hits: **22**, false alarms: **8091**, misses: **2**

## §2.5 metrics

- **Hit rate**: 91.67% (non è un gate, vedi #243)
- **Colte a parità di carico**: 4.17% (1) con il 5.00% di celle in allerta (punteggio ≥ 0.6075) — il confronto fra varianti
- **FAR**: 99.73% (non è un gate a 1 km², vedi #122)
- **Discriminazione**: 1.00 (hit rate su 91.90% di celle in allerta) (target ≥ 2.0) — **FAIL**
- **Mean lead time**: 108.0 h (target ≥ 18 h) — **PASS**

## Per comune (il metro dell'epica #345)

- Comuni con un evento: **13**
- **Colti ≥ Moderato entro 72 h**: 38.46% (5) con il 12.50% di comuni-giorno ≥ Moderato
- **Colti con il 10% di comuni-giorno in allerta**: 38.46% (5), punteggio ≥ 0.5365, carico effettivo 10.01% (target ≥ 90%) — **FAIL**

## Provenienza

| | |
|---|---|
| generato | 2026-11-25T05:54:18+00:00 |
| commit | `1fcb98c4f9212391f15c770d242ce5b2e0f2d404` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest` |
| `LIMEN_BACKTEST_AOI` | `it-umbria` |
| `LIMEN_BACKTEST_CANCELLO_INNESCO` | `0.6:0.34` |
| `LIMEN_BACKTEST_CLIMA` | `<percorso locale>` |
| `LIMEN_BACKTEST_END` | `2008-12-31T23:00:00+00:00` |
| `LIMEN_BACKTEST_HIGH_LEVEL` | `Moderate` |
| `LIMEN_BACKTEST_SORGENTI` | `IR,NR` |
| `LIMEN_BACKTEST_START` | `2008-12-01T00:00:00+00:00` |
| `LIMEN_REPORTS_DIR` | `<percorso locale>` |
