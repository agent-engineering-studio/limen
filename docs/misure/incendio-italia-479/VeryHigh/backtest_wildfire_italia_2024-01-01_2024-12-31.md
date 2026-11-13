# Limen backtest incendio — Italia

Finestra: **2024-01-01 → 2024-12-31**; soglia di allerta **VeryHigh**, orizzonte di preavviso **72 h**; verità: perimetri EFFIS. Il dettaglio di ogni regione è nel suo report.

| AOI | celle bruciate | hit rate | tasso di base | discriminazione | carico per cella | FAR (giornate-cella) | preavviso |
|---|---:|---:|---:|---:|---:|---:|---:|
| `it-abruzzo` | 25 | 0% | 1% | 0.00x | 0.2% | 100.0% | 0 h |
| `it-basilicata` | 115 | 7% | 1% | 11.85x | 0.6% | 99.9% | 36 h |
| `it-calabria` | 429 | 8% | 1% | 9.63x | 0.6% | 99.8% | 48 h |
| `it-campania` | 134 | 6% | 0% | 14.00x | 0.1% | 99.4% | 57 h |
| `it-emilia-romagna` | 0 | — | — | — | 0.0% | — | — |
| `it-friuli-venezia-giulia` | 13 | 0% | 0% | 0.00x | 0.0% | — | 0 h |
| `it-lazio` | 236 | 4% | 0% | 38.50x | 0.1% | 99.7% | 36 h |
| `it-liguria` | 19 | 0% | 0% | 0.00x | 0.0% | 100.0% | 0 h |
| `it-lombardia` | 4 | 0% | 0% | 0.00x | 0.0% | — | 0 h |
| `it-marche` | 5 | 0% | 0% | 0.00x | 0.0% | 100.0% | 0 h |
| `it-molise` | 31 | 10% | 0% | 308.00x | 0.0% | 99.1% | 0 h |
| `it-piemonte` | 10 | 0% | 0% | 0.00x | 0.0% | — | 0 h |
| `it-puglia` | 413 | 1% | 0% | 4.42x | 0.2% | 99.9% | 72 h |
| `it-sardegna` | 137 | 12% | 1% | 9.68x | 2.4% | 100.0% | 51 h |
| `it-sicilia` | 629 | 11% | 2% | 5.39x | 1.0% | 99.8% | 51 h |
| `it-toscana` | 24 | 0% | 0% | 0.00x | 0.0% | 100.0% | 0 h |
| `it-trentino-alto-adige` | 0 | — | — | — | 0.0% | — | — |
| `it-umbria` | 7 | 0% | 0% | 0.00x | 0.1% | 100.0% | 0 h |
| `it-valle-d-aosta` | 0 | — | — | — | 0.0% | — | — |
| `it-veneto` | 0 | — | — | — | 0.0% | — | — |
| **Italia** | **2231** | **7%** | **1%** | **7.44x** | | | |

Una regione senza celle bruciate non ha hit rate né FAR: non è «zero»,
è nessun incendio censito (perimetri EFFIS) nella finestra.

## Provenienza

| | |
|---|---|
| generato | 2026-11-12T20:42:17+00:00 |
| commit | `42d772137fbc3a64aaea44cddae040bd53b56ec6` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1` |
| flood | `flood-v1.3.0` |
| wildfire | `wildfire-v1.1.0` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_END` | `2024-12-31` |
| `LIMEN_BACKTEST_WILDFIRE_LEVEL` | `VeryHigh` |
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
