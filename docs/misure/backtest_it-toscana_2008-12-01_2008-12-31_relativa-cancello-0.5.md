# Limen backtest report — AOI `it-toscana` — V1

Window: **2008-12-01T00:00:00+00:00 → 2008-12-31T23:00:00+00:00**
Generated: 2026-11-25T13:09:25.262747+00:00

- Cells scored per hour: **23779**
- Configurazione: verità ogni precisione; sorgenti IR, NR; pioggia modello; antecedenti regione (riferimento nazionale); sismica spenta; cancello d'innesco: senza innesco > 0.5 il punteggio non supera 0.34; innesco cumulata 24 h / q0.999 del nodo (sostituisce, saturazione 1.0)
- Truth events (in window): **33**
- Alert-level cell-hours: **881527**
- Hits: **31**, false alarms: **22399**, misses: **2**

## §2.5 metrics

- **Hit rate**: 93.94% (non è un gate, vedi #243)
- **Colte a parità di carico**: 21.21% (7) con il 5.00% di celle in allerta (punteggio ≥ 0.6428) — il confronto fra varianti
- **FAR**: 99.86% (non è un gate a 1 km², vedi #122)
- **Discriminazione**: 1.00 (hit rate su 94.33% di celle in allerta) (target ≥ 2.0) — **FAIL**
- **Mean lead time**: 91.8 h (target ≥ 18 h) — **PASS**

## Per comune (il metro dell'epica #345)

- Comuni con un evento: **19**
- **Colti ≥ Moderato entro 72 h**: 94.74% (18) con il 12.49% di comuni-giorno ≥ Moderato
- **Colti con il 10% di comuni-giorno in allerta**: 89.47% (17), punteggio ≥ 0.5629, carico effettivo 10.00% (target ≥ 90%) — **FAIL**

## Provenienza

| | |
|---|---|
| generato | 2026-11-25T13:09:25+00:00 |
| commit | `1fcb98c4f9212391f15c770d242ce5b2e0f2d404` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest` |
| `LIMEN_BACKTEST_AOI` | `it-toscana` |
| `LIMEN_BACKTEST_CANCELLO_INNESCO` | `0.5:0.34` |
| `LIMEN_BACKTEST_CLIMA` | `<percorso locale>` |
| `LIMEN_BACKTEST_END` | `2008-12-31T23:00:00+00:00` |
| `LIMEN_BACKTEST_HIGH_LEVEL` | `Moderate` |
| `LIMEN_BACKTEST_SORGENTI` | `IR,NR` |
| `LIMEN_BACKTEST_START` | `2008-12-01T00:00:00+00:00` |
| `LIMEN_REPORTS_DIR` | `<percorso locale>` |
