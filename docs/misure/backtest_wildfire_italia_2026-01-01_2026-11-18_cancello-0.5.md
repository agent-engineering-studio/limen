# Limen backtest incendio — Italia

Finestra: **2026-01-01 → 2026-11-18**; soglia di allerta **Moderate**, orizzonte di preavviso **72 h**; verità: perimetri EFFIS. Il dettaglio di ogni regione è nel suo report.

| AOI | celle bruciate | hit rate | tasso di base | discriminazione | carico per cella | FAR (giornate-cella) | preavviso |
|---|---:|---:|---:|---:|---:|---:|---:|
| `it-abruzzo` | 238 | 80% | 22% | 3.69x | 16.2% | 99.9% | 55 h |
| `it-basilicata` | 581 | 87% | 22% | 4.02x | 24.8% | 99.8% | 66 h |
| `it-calabria` | 1044 | 64% | 18% | 3.62x | 16.0% | 99.7% | 59 h |
| `it-campania` | 418 | 59% | 18% | 3.39x | 15.9% | 99.9% | 48 h |
| `it-emilia-romagna` | 100 | 18% | 6% | 3.22x | 5.6% | 100.0% | 64 h |
| `it-friuli-venezia-giulia` | 78 | 72% | 4% | 16.95x | 3.0% | 99.9% | 46 h |
| `it-lazio` | 416 | 48% | 14% | 3.41x | 13.0% | 99.9% | 59 h |
| `it-liguria` | 66 | 70% | 17% | 4.19x | 14.3% | 100.0% | 45 h |
| `it-lombardia` | 109 | 16% | 3% | 5.21x | 2.6% | 100.0% | 45 h |
| `it-marche` | 9 | 100% | 23% | 4.35x | 11.9% | 100.0% | 72 h |
| `it-molise` | 102 | 69% | 18% | 3.88x | 19.4% | 99.9% | 66 h |
| `it-piemonte` | 279 | 46% | 9% | 5.40x | 5.1% | 99.9% | 55 h |
| `it-puglia` | 2327 | 69% | 18% | 3.88x | 16.7% | 99.6% | 54 h |
| `it-sardegna` | 418 | 72% | 19% | 3.71x | 30.2% | 100.0% | 54 h |
| `it-sicilia` | 3799 | 72% | 17% | 4.31x | 15.9% | 99.3% | 63 h |
| `it-toscana` | 78 | 35% | 15% | 2.32x | 16.6% | 100.0% | 33 h |
| `it-trentino-alto-adige` | 12 | 50% | 4% | 13.14x | 6.3% | 100.0% | 72 h |
| `it-umbria` | 21 | 33% | 12% | 2.87x | 17.5% | 100.0% | 72 h |
| `it-valle-d-aosta` | 6 | 0% | 21% | 0.00x | 11.0% | 100.0% | 0 h |
| `it-veneto` | 59 | 0% | 0% | 0.00x | 1.9% | 100.0% | 0 h |
| **Italia** | **10160** | **67%** | **17%** | **4.01x** | | | |

Una regione senza celle bruciate non ha hit rate né FAR: non è «zero»,
è nessun incendio censito (perimetri EFFIS) nella finestra.

## Provenienza

| | |
|---|---|
| generato | 2026-11-19T16:05:08+00:00 |
| commit | `9ee1201dcb1d641ea944a6bd45525396796daea5` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_CANCELLO` | `0.5` |
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
