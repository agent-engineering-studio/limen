# Limen backtest report — AOI `it-piemonte` — V1

Window: **2009-04-01T00:00:00+00:00 → 2009-04-30T23:00:00+00:00**
Generated: 2026-11-25T14:09:57.898377+00:00

- Cells scored per hour: **26140**
- Configurazione: verità ogni precisione; sorgenti IR, NR; pioggia modello; antecedenti regione (riferimento nazionale); sismica spenta; cancello d'innesco: senza innesco > 0.5 il punteggio non supera 0.34; innesco cumulata 24 h / q0.999 del nodo (sostituisce, saturazione 1.0)
- Truth events (in window): **52**
- Alert-level cell-hours: **1338416**
- Hits: **48**, false alarms: **26090**, misses: **4**

## §2.5 metrics

- **Hit rate**: 92.31% (non è un gate, vedi #243)
- **Colte a parità di carico**: 11.54% (6) con il 5.00% di celle in allerta (punteggio ≥ 0.6809) — il confronto fra varianti
- **FAR**: 99.82% (non è un gate a 1 km², vedi #122)
- **Discriminazione**: 0.92 (hit rate su 99.99% di celle in allerta) (target ≥ 2.0) — **FAIL**
- **Mean lead time**: 21.9 h (target ≥ 18 h) — **PASS**

## Per comune (il metro dell'epica #345)

- Comuni con un evento: **41**
- **Colti ≥ Moderato entro 72 h**: 90.24% (37) con il 13.40% di comuni-giorno ≥ Moderato
- **Colti con il 10% di comuni-giorno in allerta**: 90.24% (37), punteggio ≥ 0.5006, carico effettivo 10.00% (target ≥ 90%) — **PASS**

## Provenienza

| | |
|---|---|
| generato | 2026-11-25T14:09:57+00:00 |
| commit | `1fcb98c4f9212391f15c770d242ce5b2e0f2d404` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest` |
| `LIMEN_BACKTEST_AOI` | `it-piemonte` |
| `LIMEN_BACKTEST_CANCELLO_INNESCO` | `0.5:0.34` |
| `LIMEN_BACKTEST_CLIMA` | `<percorso locale>` |
| `LIMEN_BACKTEST_END` | `2009-04-30T23:00:00+00:00` |
| `LIMEN_BACKTEST_HIGH_LEVEL` | `Moderate` |
| `LIMEN_BACKTEST_SORGENTI` | `IR,NR` |
| `LIMEN_BACKTEST_START` | `2009-04-01T00:00:00+00:00` |
| `LIMEN_REPORTS_DIR` | `<percorso locale>` |
