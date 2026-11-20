# Limen backtest incendio — Italia

Finestra: **2026-01-01 → 2026-11-18**; soglia di allerta **Moderate**, orizzonte di preavviso **72 h**; verità: perimetri EFFIS. Il dettaglio di ogni regione è nel suo report.

| AOI | celle bruciate | hit rate | tasso di base | discriminazione | carico per cella | FAR (giornate-cella) | preavviso |
|---|---:|---:|---:|---:|---:|---:|---:|
| `it-abruzzo` | 238 | 98% | 34% | 2.88x | 29.7% | 99.9% | 64 h |
| `it-basilicata` | 581 | 98% | 40% | 2.45x | 39.1% | 99.8% | 70 h |
| `it-calabria` | 1044 | 91% | 34% | 2.66x | 30.2% | 99.8% | 68 h |
| `it-campania` | 418 | 91% | 35% | 2.59x | 33.7% | 99.9% | 61 h |
| `it-emilia-romagna` | 100 | 65% | 24% | 2.76x | 23.9% | 100.0% | 54 h |
| `it-friuli-venezia-giulia` | 78 | 76% | 12% | 6.38x | 11.3% | 100.0% | 61 h |
| `it-lazio` | 416 | 90% | 33% | 2.72x | 30.3% | 99.9% | 62 h |
| `it-liguria` | 66 | 86% | 30% | 2.93x | 25.3% | 100.0% | 56 h |
| `it-lombardia` | 109 | 31% | 12% | 2.54x | 14.0% | 100.0% | 56 h |
| `it-marche` | 9 | 100% | 27% | 3.69x | 30.8% | 100.0% | 72 h |
| `it-molise` | 102 | 84% | 36% | 2.33x | 35.3% | 99.9% | 67 h |
| `it-piemonte` | 279 | 67% | 16% | 4.22x | 16.8% | 100.0% | 58 h |
| `it-puglia` | 2327 | 95% | 38% | 2.49x | 35.8% | 99.6% | 69 h |
| `it-sardegna` | 418 | 89% | 37% | 2.39x | 40.3% | 100.0% | 70 h |
| `it-sicilia` | 3799 | 89% | 33% | 2.68x | 31.6% | 99.5% | 69 h |
| `it-toscana` | 78 | 67% | 31% | 2.15x | 33.3% | 100.0% | 48 h |
| `it-trentino-alto-adige` | 12 | 50% | 8% | 6.21x | 11.3% | 100.0% | 72 h |
| `it-umbria` | 21 | 33% | 21% | 1.61x | 33.8% | 100.0% | 72 h |
| `it-valle-d-aosta` | 6 | 0% | 34% | 0.00x | 15.9% | 100.0% | 0 h |
| `it-veneto` | 59 | 32% | 10% | 3.36x | 13.4% | 100.0% | 52 h |
| **Italia** | **10160** | **89%** | **34%** | **2.63x** | | | |

Una regione senza celle bruciate non ha hit rate né FAR: non è «zero»,
è nessun incendio censito (perimetri EFFIS) nella finestra.

## Provenienza

| | |
|---|---|
| generato | 2026-11-19T21:15:25+00:00 |
| commit | `b2f7b2157a4f9b7cc42ee0786f4ee443ff871bc6` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_CANCELLO` | `0.3` |
| `LIMEN_BACKTEST_WILDFIRE_END` | `2026-11-18` |
| `LIMEN_BACKTEST_WILDFIRE_LEVEL` | `Moderate` |
| `LIMEN_BACKTEST_WILDFIRE_START` | `2026-01-01` |
| `LIMEN_BACKTEST_WILDFIRE_TETTO` | `95:35:6-9` |
| `LIMEN_BACKUP_DIR` | `<percorso locale>` |
| `LIMEN_DATA_ROOT` | `<percorso locale>` |
| `LIMEN_DOMINIO` | `localhost` |
| `LIMEN_IMAGE_PREFIX` | `ghcr.io/agent-engineering-studio/limen-` |
| `LIMEN_IMAGE_TAG` | `sha-9b96afc` |
| `LIMEN_IMPERVIOUSNESS_RASTER` | `<percorso locale>` |
| `LIMEN_PROXY_BIND` | `127.0.0.1` |
| `LIMEN_REPORTS_DIR` | `<percorso locale>` |
