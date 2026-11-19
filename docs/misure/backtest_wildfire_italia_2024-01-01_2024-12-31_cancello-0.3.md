# Limen backtest incendio — Italia

Finestra: **2024-01-01 → 2024-12-31**; soglia di allerta **Moderate**, orizzonte di preavviso **72 h**; verità: perimetri EFFIS. Il dettaglio di ogni regione è nel suo report.

| AOI | celle bruciate | hit rate | tasso di base | discriminazione | carico per cella | FAR (giornate-cella) | preavviso |
|---|---:|---:|---:|---:|---:|---:|---:|
| `it-abruzzo` | 25 | 48% | 12% | 4.07x | 12.2% | 100.0% | 72 h |
| `it-basilicata` | 115 | 97% | 27% | 3.55x | 25.8% | 99.9% | 72 h |
| `it-calabria` | 429 | 85% | 24% | 3.51x | 20.7% | 99.9% | 65 h |
| `it-campania` | 134 | 81% | 17% | 4.76x | 14.5% | 99.9% | 66 h |
| `it-emilia-romagna` | 0 | — | — | — | 0.0% | — | — |
| `it-friuli-venezia-giulia` | 13 | 0% | 0% | 0.00x | 1.5% | 100.0% | 0 h |
| `it-lazio` | 236 | 93% | 20% | 4.57x | 15.9% | 99.9% | 68 h |
| `it-liguria` | 19 | 0% | 5% | 0.00x | 3.4% | 100.0% | 0 h |
| `it-lombardia` | 4 | 0% | 0% | 0.00x | 0.5% | 100.0% | 0 h |
| `it-marche` | 5 | 100% | 19% | 5.20x | 15.2% | 100.0% | 72 h |
| `it-molise` | 31 | 97% | 21% | 4.70x | 15.7% | 99.9% | 72 h |
| `it-piemonte` | 10 | 0% | 1% | 0.00x | 0.8% | 100.0% | 0 h |
| `it-puglia` | 413 | 86% | 25% | 3.40x | 23.2% | 99.9% | 62 h |
| `it-sardegna` | 137 | 94% | 31% | 3.00x | 30.6% | 100.0% | 67 h |
| `it-sicilia` | 629 | 75% | 29% | 2.57x | 28.8% | 99.9% | 69 h |
| `it-toscana` | 24 | 88% | 9% | 9.37x | 13.3% | 100.0% | 65 h |
| `it-trentino-alto-adige` | 0 | — | — | — | 0.0% | — | — |
| `it-umbria` | 7 | 100% | 17% | 5.84x | 17.3% | 100.0% | 72 h |
| `it-valle-d-aosta` | 0 | — | — | — | 0.0% | — | — |
| `it-veneto` | 0 | — | — | — | 0.0% | — | — |
| **Italia** | **2231** | **82%** | **25%** | **3.32x** | | | |

Una regione senza celle bruciate non ha hit rate né FAR: non è «zero»,
è nessun incendio censito (perimetri EFFIS) nella finestra.

## Provenienza

| | |
|---|---|
| generato | 2026-11-19T15:22:03+00:00 |
| commit | `9ee1201dcb1d641ea944a6bd45525396796daea5` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_CANCELLO` | `0.3` |
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
