# Limen backtest incendio — Italia

Finestra: **2024-01-01 → 2024-12-31**; soglia di allerta **High**, orizzonte di preavviso **72 h**; verità: perimetri EFFIS. Il dettaglio di ogni regione è nel suo report.

| AOI | celle bruciate | hit rate | tasso di base | discriminazione | carico per cella | FAR (giornate-cella) | preavviso |
|---|---:|---:|---:|---:|---:|---:|---:|
| `it-abruzzo` | 25 | 40% | 5% | 7.46x | 4.1% | 100.0% | 72 h |
| `it-basilicata` | 115 | 89% | 13% | 6.74x | 12.9% | 99.9% | 60 h |
| `it-calabria` | 429 | 54% | 10% | 5.26x | 8.3% | 99.8% | 55 h |
| `it-campania` | 134 | 56% | 7% | 7.86x | 4.8% | 99.9% | 48 h |
| `it-emilia-romagna` | 0 | — | — | — | 0.0% | — | — |
| `it-friuli-venezia-giulia` | 13 | 0% | 0% | 0.00x | 0.1% | 100.0% | 0 h |
| `it-lazio` | 236 | 70% | 7% | 9.53x | 5.6% | 99.9% | 59 h |
| `it-liguria` | 19 | 0% | 0% | 0.00x | 0.3% | 100.0% | 0 h |
| `it-lombardia` | 4 | 0% | 0% | 0.00x | 0.0% | 100.0% | 0 h |
| `it-marche` | 5 | 0% | 3% | 0.00x | 3.5% | 100.0% | 0 h |
| `it-molise` | 31 | 97% | 7% | 13.43x | 4.3% | 99.9% | 50 h |
| `it-piemonte` | 10 | 0% | 0% | 0.00x | 0.0% | 100.0% | 0 h |
| `it-puglia` | 413 | 62% | 11% | 5.60x | 9.1% | 99.9% | 55 h |
| `it-sardegna` | 137 | 83% | 16% | 5.33x | 16.1% | 100.0% | 60 h |
| `it-sicilia` | 629 | 61% | 15% | 4.15x | 12.8% | 99.9% | 67 h |
| `it-toscana` | 24 | 8% | 2% | 5.13x | 4.0% | 100.0% | 0 h |
| `it-trentino-alto-adige` | 0 | — | — | — | 0.0% | — | — |
| `it-umbria` | 7 | 100% | 6% | 15.62x | 7.1% | 100.0% | 51 h |
| `it-valle-d-aosta` | 0 | — | — | — | 0.0% | — | — |
| `it-veneto` | 0 | — | — | — | 0.0% | — | — |
| **Italia** | **2231** | **62%** | **11%** | **5.50x** | | | |

Una regione senza celle bruciate non ha hit rate né FAR: non è «zero»,
è nessun incendio censito (perimetri EFFIS) nella finestra.

## Provenienza

| | |
|---|---|
| generato | 2026-11-12T18:17:26+00:00 |
| commit | `42d772137fbc3a64aaea44cddae040bd53b56ec6` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1` |
| flood | `flood-v1.3.0` |
| wildfire | `wildfire-v1.1.0` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_END` | `2024-12-31` |
| `LIMEN_BACKTEST_WILDFIRE_LEVEL` | `High` |
| `LIMEN_BACKTEST_WILDFIRE_START` | `2024-01-01` |
| `LIMEN_BACKUP_DIR` | `<percorso locale>` |
| `LIMEN_DATA_ROOT` | `<percorso locale>` |
| `LIMEN_DOMINIO` | `localhost` |
| `LIMEN_IMAGE_PREFIX` | `ghcr.io/agent-engineering-studio/limen-` |
| `LIMEN_IMAGE_TAG` | `sha-e9e867e` |
| `LIMEN_IMPERVIOUSNESS_RASTER` | `<percorso locale>` |
| `LIMEN_MINIO_ROOT_USER` | `limen-admin` |
| `LIMEN_PROXY_BIND` | `127.0.0.1` |
| `LIMEN_REPORTS_DIR` | `<percorso locale>` |
