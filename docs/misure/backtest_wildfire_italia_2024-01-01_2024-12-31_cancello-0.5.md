# Limen backtest incendio — Italia

Finestra: **2024-01-01 → 2024-12-31**; soglia di allerta **Moderate**, orizzonte di preavviso **72 h**; verità: perimetri EFFIS. Il dettaglio di ogni regione è nel suo report.

| AOI | celle bruciate | hit rate | tasso di base | discriminazione | carico per cella | FAR (giornate-cella) | preavviso |
|---|---:|---:|---:|---:|---:|---:|---:|
| `it-abruzzo` | 25 | 44% | 11% | 4.11x | 8.7% | 100.0% | 72 h |
| `it-basilicata` | 115 | 89% | 16% | 5.48x | 17.5% | 99.9% | 62 h |
| `it-calabria` | 429 | 64% | 16% | 3.98x | 13.9% | 99.9% | 61 h |
| `it-campania` | 134 | 68% | 13% | 5.39x | 8.6% | 99.9% | 59 h |
| `it-emilia-romagna` | 0 | — | — | — | 0.0% | — | — |
| `it-friuli-venezia-giulia` | 13 | 0% | 0% | 0.00x | 1.1% | 100.0% | 0 h |
| `it-lazio` | 236 | 72% | 15% | 4.72x | 8.9% | 99.9% | 68 h |
| `it-liguria` | 19 | 0% | 5% | 0.00x | 3.2% | 100.0% | 0 h |
| `it-lombardia` | 4 | 0% | 0% | 0.00x | 0.4% | 100.0% | 0 h |
| `it-marche` | 5 | 0% | 3% | 0.00x | 6.1% | 100.0% | 0 h |
| `it-molise` | 31 | 97% | 10% | 9.62x | 7.9% | 99.9% | 50 h |
| `it-piemonte` | 10 | 0% | 1% | 0.00x | 0.7% | 100.0% | 0 h |
| `it-puglia` | 413 | 62% | 13% | 4.80x | 10.7% | 99.9% | 56 h |
| `it-sardegna` | 137 | 83% | 22% | 3.75x | 24.1% | 100.0% | 62 h |
| `it-sicilia` | 629 | 64% | 20% | 3.28x | 16.0% | 99.9% | 67 h |
| `it-toscana` | 24 | 46% | 4% | 11.64x | 8.6% | 100.0% | 72 h |
| `it-trentino-alto-adige` | 0 | — | — | — | 0.0% | — | — |
| `it-umbria` | 7 | 100% | 6% | 15.62x | 11.2% | 100.0% | 51 h |
| `it-valle-d-aosta` | 0 | — | — | — | 0.0% | — | — |
| `it-veneto` | 0 | — | — | — | 0.0% | — | — |
| **Italia** | **2231** | **66%** | **16%** | **4.13x** | | | |

Una regione senza celle bruciate non ha hit rate né FAR: non è «zero»,
è nessun incendio censito (perimetri EFFIS) nella finestra.

## Provenienza

| | |
|---|---|
| generato | 2026-11-19T15:08:01+00:00 |
| commit | `9ee1201dcb1d641ea944a6bd45525396796daea5` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_CANCELLO` | `0.5` |
| `LIMEN_BACKTEST_WILDFIRE_END` | `2024-12-31` |
| `LIMEN_BACKTEST_WILDFIRE_LEVEL` | `Moderate` |
| `LIMEN_BACKTEST_WILDFIRE_START` | `2024-01-01` |
| `LIMEN_BACKUP_DIR` | `<percorso locale>` |
| `LIMEN_DATA_ROOT` | `<percorso locale>` |
| `LIMEN_DOMINIO` | `localhost` |
| `LIMEN_IMAGE_PREFIX` | `ghcr.io/agent-engineering-studio/limen-` |
| `LIMEN_IMAGE_TAG` | `sha-9b96afc` |
| `LIMEN_IMPERVIOUSNESS_RASTER` | `<percorso locale>` |
| `LIMEN_PROXY_BIND` | `127.0.0.1` |
| `LIMEN_REPORTS_DIR` | `<percorso locale>` |
