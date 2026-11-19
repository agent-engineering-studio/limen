# Limen backtest incendio — Italia

Finestra: **2025-01-01 → 2025-12-31**; soglia di allerta **Moderate**, orizzonte di preavviso **72 h**; verità: perimetri EFFIS. Il dettaglio di ogni regione è nel suo report.

| AOI | celle bruciate | hit rate | tasso di base | discriminazione | carico per cella | FAR (giornate-cella) | preavviso |
|---|---:|---:|---:|---:|---:|---:|---:|
| `it-abruzzo` | 48 | 79% | 20% | 4.03x | 13.4% | 100.0% | 52 h |
| `it-basilicata` | 339 | 98% | 29% | 3.36x | 27.6% | 99.9% | 68 h |
| `it-calabria` | 673 | 81% | 20% | 4.15x | 18.8% | 99.8% | 64 h |
| `it-campania` | 221 | 80% | 15% | 5.29x | 13.8% | 99.9% | 65 h |
| `it-emilia-romagna` | 22 | 18% | 6% | 3.27x | 5.4% | 100.0% | 72 h |
| `it-friuli-venezia-giulia` | 0 | — | — | — | 0.0% | — | — |
| `it-lazio` | 142 | 70% | 13% | 5.27x | 12.9% | 100.0% | 64 h |
| `it-liguria` | 0 | — | — | — | 0.0% | — | — |
| `it-lombardia` | 11 | 0% | 1% | 0.00x | 1.0% | 100.0% | 0 h |
| `it-marche` | 4 | 0% | 13% | 0.00x | 13.1% | 100.0% | 0 h |
| `it-molise` | 78 | 100% | 20% | 5.02x | 17.8% | 99.9% | 60 h |
| `it-piemonte` | 12 | 17% | 1% | 12.81x | 1.8% | 100.0% | 72 h |
| `it-puglia` | 872 | 95% | 26% | 3.60x | 25.1% | 99.8% | 67 h |
| `it-sardegna` | 182 | 93% | 33% | 2.80x | 30.8% | 100.0% | 67 h |
| `it-sicilia` | 1699 | 90% | 28% | 3.27x | 23.8% | 99.8% | 67 h |
| `it-toscana` | 29 | 90% | 12% | 7.54x | 11.3% | 100.0% | 66 h |
| `it-trentino-alto-adige` | 15 | 0% | 0% | 0.00x | 1.6% | 100.0% | 0 h |
| `it-umbria` | 0 | — | — | — | 0.0% | — | — |
| `it-valle-d-aosta` | 0 | — | — | — | 0.0% | — | — |
| `it-veneto` | 0 | — | — | — | 0.0% | — | — |
| **Italia** | **4347** | **88%** | **25%** | **3.58x** | | | |

Una regione senza celle bruciate non ha hit rate né FAR: non è «zero»,
è nessun incendio censito (perimetri EFFIS) nella finestra.

## Provenienza

| | |
|---|---|
| generato | 2026-11-19T15:50:56+00:00 |
| commit | `9ee1201dcb1d641ea944a6bd45525396796daea5` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_CANCELLO` | `0.3` |
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
