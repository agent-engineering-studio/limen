# Limen backtest incendio — Italia

Finestra: **2024-01-01 → 2024-12-31**; soglia di allerta **Moderate**, orizzonte di preavviso **72 h**; verità: perimetri EFFIS. Il dettaglio di ogni regione è nel suo report.

| AOI | celle bruciate | hit rate | tasso di base | discriminazione | carico per cella | FAR (giornate-cella) | preavviso |
|---|---:|---:|---:|---:|---:|---:|---:|
| `it-abruzzo` | 25 | 68% | 16% | 4.32x | 17.6% | 100.0% | 72 h |
| `it-basilicata` | 115 | 97% | 29% | 3.32x | 29.3% | 100.0% | 72 h |
| `it-calabria` | 429 | 91% | 33% | 2.76x | 28.7% | 99.9% | 67 h |
| `it-campania` | 134 | 93% | 23% | 4.10x | 19.8% | 99.9% | 67 h |
| `it-emilia-romagna` | 0 | — | — | — | 0.0% | — | — |
| `it-friuli-venezia-giulia` | 13 | 0% | 3% | 0.00x | 4.4% | 100.0% | 0 h |
| `it-lazio` | 236 | 94% | 25% | 3.69x | 20.3% | 99.9% | 70 h |
| `it-liguria` | 19 | 32% | 11% | 2.96x | 7.9% | 100.0% | 0 h |
| `it-lombardia` | 4 | 0% | 1% | 0.00x | 2.0% | 100.0% | 0 h |
| `it-marche` | 5 | 100% | 25% | 4.07x | 21.3% | 100.0% | 72 h |
| `it-molise` | 31 | 97% | 23% | 4.26x | 20.6% | 100.0% | 72 h |
| `it-piemonte` | 10 | 0% | 3% | 0.00x | 2.8% | 100.0% | 0 h |
| `it-puglia` | 413 | 87% | 26% | 3.29x | 25.0% | 99.9% | 61 h |
| `it-sardegna` | 137 | 99% | 33% | 3.05x | 32.7% | 100.0% | 64 h |
| `it-sicilia` | 629 | 78% | 32% | 2.41x | 32.3% | 99.9% | 68 h |
| `it-toscana` | 24 | 88% | 14% | 6.26x | 17.9% | 100.0% | 65 h |
| `it-trentino-alto-adige` | 0 | — | — | — | 0.0% | — | — |
| `it-umbria` | 7 | 100% | 19% | 5.16x | 21.6% | 100.0% | 72 h |
| `it-valle-d-aosta` | 0 | — | — | — | 0.0% | — | — |
| `it-veneto` | 0 | — | — | — | 0.0% | — | — |
| **Italia** | **2231** | **86%** | **29%** | **2.99x** | | | |

Una regione senza celle bruciate non ha hit rate né FAR: non è «zero»,
è nessun incendio censito (perimetri EFFIS) nella finestra.

## Provenienza

| | |
|---|---|
| generato | 2026-11-19T20:46:34+00:00 |
| commit | `b2f7b2157a4f9b7cc42ee0786f4ee443ff871bc6` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_CANCELLO` | `0.3` |
| `LIMEN_BACKTEST_WILDFIRE_END` | `2024-12-31` |
| `LIMEN_BACKTEST_WILDFIRE_LEVEL` | `Moderate` |
| `LIMEN_BACKTEST_WILDFIRE_START` | `2024-01-01` |
| `LIMEN_BACKTEST_WILDFIRE_TETTO` | `95:35:6-9` |
| `LIMEN_BACKUP_DIR` | `<percorso locale>` |
| `LIMEN_DATA_ROOT` | `<percorso locale>` |
| `LIMEN_DOMINIO` | `localhost` |
| `LIMEN_IMAGE_PREFIX` | `ghcr.io/agent-engineering-studio/limen-` |
| `LIMEN_IMAGE_TAG` | `sha-9b96afc` |
| `LIMEN_IMPERVIOUSNESS_RASTER` | `<percorso locale>` |
| `LIMEN_PROXY_BIND` | `127.0.0.1` |
| `LIMEN_REPORTS_DIR` | `<percorso locale>` |
