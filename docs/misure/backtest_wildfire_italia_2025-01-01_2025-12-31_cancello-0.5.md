# Limen backtest incendio — Italia

Finestra: **2025-01-01 → 2025-12-31**; soglia di allerta **Moderate**, orizzonte di preavviso **72 h**; verità: perimetri EFFIS. Il dettaglio di ogni regione è nel suo report.

| AOI | celle bruciate | hit rate | tasso di base | discriminazione | carico per cella | FAR (giornate-cella) | preavviso |
|---|---:|---:|---:|---:|---:|---:|---:|
| `it-abruzzo` | 48 | 48% | 12% | 3.90x | 9.3% | 100.0% | 55 h |
| `it-basilicata` | 339 | 83% | 17% | 4.96x | 19.6% | 99.9% | 54 h |
| `it-calabria` | 673 | 70% | 13% | 5.47x | 13.2% | 99.8% | 53 h |
| `it-campania` | 221 | 67% | 13% | 5.17x | 7.8% | 99.9% | 64 h |
| `it-emilia-romagna` | 22 | 14% | 3% | 5.26x | 2.2% | 100.0% | 72 h |
| `it-friuli-venezia-giulia` | 0 | — | — | — | 0.0% | — | — |
| `it-lazio` | 142 | 47% | 10% | 4.91x | 7.0% | 99.9% | 62 h |
| `it-liguria` | 0 | — | — | — | 0.0% | — | — |
| `it-lombardia` | 11 | 0% | 1% | 0.00x | 0.6% | 100.0% | 0 h |
| `it-marche` | 4 | 0% | 1% | 0.00x | 6.2% | 100.0% | 0 h |
| `it-molise` | 78 | 53% | 7% | 7.62x | 9.3% | 99.9% | 53 h |
| `it-piemonte` | 12 | 8% | 1% | 8.30x | 1.4% | 100.0% | 72 h |
| `it-puglia` | 872 | 84% | 14% | 6.11x | 13.3% | 99.8% | 59 h |
| `it-sardegna` | 182 | 84% | 22% | 3.86x | 24.3% | 100.0% | 61 h |
| `it-sicilia` | 1699 | 70% | 17% | 4.26x | 13.8% | 99.7% | 58 h |
| `it-toscana` | 29 | 52% | 3% | 16.69x | 7.8% | 100.0% | 62 h |
| `it-trentino-alto-adige` | 15 | 0% | 0% | 0.00x | 1.5% | 100.0% | 0 h |
| `it-umbria` | 0 | — | — | — | 0.0% | — | — |
| `it-valle-d-aosta` | 0 | — | — | — | 0.0% | — | — |
| `it-veneto` | 0 | — | — | — | 0.0% | — | — |
| **Italia** | **4347** | **72%** | **15%** | **4.90x** | | | |

Una regione senza celle bruciate non ha hit rate né FAR: non è «zero»,
è nessun incendio censito (perimetri EFFIS) nella finestra.

## Provenienza

| | |
|---|---|
| generato | 2026-11-19T15:36:40+00:00 |
| commit | `9ee1201dcb1d641ea944a6bd45525396796daea5` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_CANCELLO` | `0.5` |
| `LIMEN_BACKTEST_WILDFIRE_END` | `2025-12-31` |
| `LIMEN_BACKTEST_WILDFIRE_LEVEL` | `Moderate` |
| `LIMEN_BACKTEST_WILDFIRE_START` | `2025-01-01` |
| `LIMEN_BACKUP_DIR` | `<percorso locale>` |
| `LIMEN_DATA_ROOT` | `<percorso locale>` |
| `LIMEN_DOMINIO` | `localhost` |
| `LIMEN_IMAGE_PREFIX` | `ghcr.io/agent-engineering-studio/limen-` |
| `LIMEN_IMAGE_TAG` | `sha-9b96afc` |
| `LIMEN_IMPERVIOUSNESS_RASTER` | `<percorso locale>` |
| `LIMEN_PROXY_BIND` | `127.0.0.1` |
| `LIMEN_REPORTS_DIR` | `<percorso locale>` |
