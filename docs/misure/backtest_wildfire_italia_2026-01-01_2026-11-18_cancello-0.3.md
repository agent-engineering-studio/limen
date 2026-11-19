# Limen backtest incendio — Italia

Finestra: **2026-01-01 → 2026-11-18**; soglia di allerta **Moderate**, orizzonte di preavviso **72 h**; verità: perimetri EFFIS. Il dettaglio di ogni regione è nel suo report.

| AOI | celle bruciate | hit rate | tasso di base | discriminazione | carico per cella | FAR (giornate-cella) | preavviso |
|---|---:|---:|---:|---:|---:|---:|---:|
| `it-abruzzo` | 238 | 96% | 28% | 3.42x | 23.3% | 99.9% | 62 h |
| `it-basilicata` | 581 | 98% | 39% | 2.52x | 36.3% | 99.8% | 69 h |
| `it-calabria` | 1044 | 86% | 27% | 3.22x | 23.3% | 99.7% | 64 h |
| `it-campania` | 418 | 83% | 28% | 2.95x | 27.4% | 99.9% | 56 h |
| `it-emilia-romagna` | 100 | 38% | 15% | 2.59x | 14.8% | 100.0% | 66 h |
| `it-friuli-venezia-giulia` | 78 | 72% | 4% | 16.65x | 4.9% | 99.9% | 46 h |
| `it-lazio` | 416 | 87% | 26% | 3.28x | 23.8% | 99.9% | 58 h |
| `it-liguria` | 66 | 82% | 20% | 4.18x | 15.8% | 100.0% | 49 h |
| `it-lombardia` | 109 | 20% | 6% | 3.32x | 6.7% | 100.0% | 51 h |
| `it-marche` | 9 | 100% | 23% | 4.35x | 24.2% | 100.0% | 72 h |
| `it-molise` | 102 | 84% | 32% | 2.66x | 30.4% | 99.9% | 67 h |
| `it-piemonte` | 279 | 48% | 10% | 4.95x | 9.7% | 100.0% | 55 h |
| `it-puglia` | 2327 | 95% | 37% | 2.55x | 34.4% | 99.6% | 69 h |
| `it-sardegna` | 418 | 88% | 36% | 2.44x | 38.8% | 100.0% | 70 h |
| `it-sicilia` | 3799 | 87% | 31% | 2.81x | 28.7% | 99.5% | 69 h |
| `it-toscana` | 78 | 56% | 21% | 2.63x | 24.4% | 100.0% | 30 h |
| `it-trentino-alto-adige` | 12 | 50% | 4% | 13.14x | 6.6% | 100.0% | 72 h |
| `it-umbria` | 21 | 33% | 16% | 2.03x | 26.6% | 100.0% | 72 h |
| `it-valle-d-aosta` | 6 | 0% | 26% | 0.00x | 11.5% | 100.0% | 0 h |
| `it-veneto` | 59 | 14% | 4% | 3.68x | 6.0% | 100.0% | 27 h |
| **Italia** | **10160** | **86%** | **31%** | **2.81x** | | | |

Una regione senza celle bruciate non ha hit rate né FAR: non è «zero»,
è nessun incendio censito (perimetri EFFIS) nella finestra.

## Provenienza

| | |
|---|---|
| generato | 2026-11-19T16:20:54+00:00 |
| commit | `9ee1201dcb1d641ea944a6bd45525396796daea5` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_CANCELLO` | `0.3` |
| `LIMEN_BACKTEST_WILDFIRE_END` | `2026-11-18` |
| `LIMEN_BACKTEST_WILDFIRE_LEVEL` | `Moderate` |
| `LIMEN_BACKTEST_WILDFIRE_START` | `2026-01-01` |
| `LIMEN_BACKUP_DIR` | `<percorso locale>` |
| `LIMEN_DATA_ROOT` | `<percorso locale>` |
| `LIMEN_DOMINIO` | `localhost` |
| `LIMEN_IMAGE_PREFIX` | `ghcr.io/agent-engineering-studio/limen-` |
| `LIMEN_IMAGE_TAG` | `sha-9b96afc` |
| `LIMEN_IMPERVIOUSNESS_RASTER` | `<percorso locale>` |
| `LIMEN_PROXY_BIND` | `127.0.0.1` |
| `LIMEN_REPORTS_DIR` | `<percorso locale>` |
