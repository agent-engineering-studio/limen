# Limen backtest incendio — Italia

Finestra: **2026-01-01 → 2026-11-10**; soglia di allerta **VeryHigh**, orizzonte di preavviso **72 h**; verità: perimetri EFFIS. Il dettaglio di ogni regione è nel suo report.

| AOI | celle bruciate | hit rate | tasso di base | discriminazione | carico per cella | FAR (giornate-cella) | preavviso |
|---|---:|---:|---:|---:|---:|---:|---:|
| `it-abruzzo` | 238 | 23% | 2% | 13.35x | 0.8% | 99.5% | 47 h |
| `it-basilicata` | 581 | 3% | 1% | 6.20x | 1.2% | 99.9% | 53 h |
| `it-calabria` | 1044 | 9% | 1% | 7.45x | 1.1% | 99.4% | 64 h |
| `it-campania` | 418 | 4% | 0% | 14.06x | 0.3% | 99.8% | 19 h |
| `it-emilia-romagna` | 100 | 0% | 0% | 0.00x | 0.0% | 100.0% | 0 h |
| `it-friuli-venezia-giulia` | 78 | 0% | 0% | 0.00x | 0.0% | 100.0% | 0 h |
| `it-lazio` | 416 | 0% | 0% | 0.00x | 0.1% | 100.0% | 0 h |
| `it-liguria` | 66 | 0% | 0% | 0.00x | 0.0% | 100.0% | 0 h |
| `it-lombardia` | 109 | 0% | 0% | 0.00x | 0.0% | 100.0% | 0 h |
| `it-marche` | 9 | 100% | 0% | 201.86x | 0.2% | 99.8% | 37 h |
| `it-molise` | 102 | 1% | 0% | 20.93x | 0.3% | 100.0% | 48 h |
| `it-piemonte` | 279 | 0% | 0% | 0.00x | 0.0% | 100.0% | 0 h |
| `it-puglia` | 2327 | 2% | 0% | 6.37x | 0.3% | 99.3% | 67 h |
| `it-sardegna` | 418 | 8% | 1% | 7.90x | 3.9% | 100.0% | 38 h |
| `it-sicilia` | 3799 | 9% | 1% | 9.52x | 0.9% | 98.7% | 58 h |
| `it-toscana` | 78 | 0% | 0% | 0.00x | 0.1% | 100.0% | 0 h |
| `it-trentino-alto-adige` | 12 | 0% | 0% | 0.00x | 0.0% | 100.0% | 0 h |
| `it-umbria` | 21 | 5% | 0% | 10.83x | 0.3% | 100.0% | 72 h |
| `it-valle-d-aosta` | 6 | 0% | 2% | 0.00x | 0.3% | 100.0% | 0 h |
| `it-veneto` | 59 | 0% | 0% | 0.00x | 0.0% | 100.0% | 0 h |
| **Italia** | **10160** | **6%** | **1%** | **8.88x** | | | |

Una regione senza celle bruciate non ha hit rate né FAR: non è «zero»,
è nessun incendio censito (perimetri EFFIS) nella finestra.

## Provenienza

| | |
|---|---|
| generato | 2026-11-12T21:56:01+00:00 |
| commit | `42d772137fbc3a64aaea44cddae040bd53b56ec6` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1` |
| flood | `flood-v1.3.0` |
| wildfire | `wildfire-v1.1.0` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_END` | `2026-11-10` |
| `LIMEN_BACKTEST_WILDFIRE_LEVEL` | `VeryHigh` |
| `LIMEN_BACKTEST_WILDFIRE_START` | `2026-01-01` |
| `LIMEN_BACKUP_DIR` | `<percorso locale>` |
| `LIMEN_DATA_ROOT` | `<percorso locale>` |
| `LIMEN_DOMINIO` | `localhost` |
| `LIMEN_IMAGE_PREFIX` | `ghcr.io/agent-engineering-studio/limen-` |
| `LIMEN_IMAGE_TAG` | `sha-e9e867e` |
| `LIMEN_IMPERVIOUSNESS_RASTER` | `<percorso locale>` |
| `LIMEN_MINIO_ROOT_USER` | `limen-admin` |
| `LIMEN_PROXY_BIND` | `127.0.0.1` |
| `LIMEN_REPORTS_DIR` | `<percorso locale>` |
