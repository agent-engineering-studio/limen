# Limen backtest incendio — Italia

Finestra: **2025-01-01 → 2025-12-31**; soglia di allerta **VeryHigh**, orizzonte di preavviso **72 h**; verità: perimetri EFFIS. Il dettaglio di ogni regione è nel suo report.

| AOI | celle bruciate | hit rate | tasso di base | discriminazione | carico per cella | FAR (giornate-cella) | preavviso |
|---|---:|---:|---:|---:|---:|---:|---:|
| `it-abruzzo` | 48 | 8% | 0% | 17.80x | 0.1% | 99.9% | 0 h |
| `it-basilicata` | 339 | 3% | 0% | 7.84x | 0.9% | 99.9% | 70 h |
| `it-calabria` | 673 | 7% | 1% | 11.89x | 0.8% | 99.8% | 44 h |
| `it-campania` | 221 | 4% | 0% | 13.04x | 0.1% | 99.8% | 18 h |
| `it-emilia-romagna` | 22 | 0% | 0% | 0.00x | 0.0% | 100.0% | 0 h |
| `it-friuli-venezia-giulia` | 0 | — | — | — | 0.0% | — | — |
| `it-lazio` | 142 | 0% | 0% | 0.00x | 0.0% | 100.0% | 0 h |
| `it-liguria` | 0 | — | — | — | 0.0% | — | — |
| `it-lombardia` | 11 | 0% | 0% | 0.00x | 0.0% | — | 0 h |
| `it-marche` | 4 | 0% | 0% | 0.00x | 0.1% | 100.0% | 0 h |
| `it-molise` | 78 | 0% | 0% | 0.00x | 0.1% | 100.0% | 0 h |
| `it-piemonte` | 12 | 0% | 0% | 0.00x | 0.0% | 100.0% | 0 h |
| `it-puglia` | 872 | 4% | 0% | 17.05x | 0.2% | 99.6% | 41 h |
| `it-sardegna` | 182 | 9% | 1% | 7.01x | 2.9% | 100.0% | 59 h |
| `it-sicilia` | 1699 | 9% | 1% | 6.23x | 0.8% | 99.5% | 56 h |
| `it-toscana` | 29 | 0% | 0% | 0.00x | 0.0% | 100.0% | 0 h |
| `it-trentino-alto-adige` | 15 | 0% | 0% | 0.00x | 0.0% | — | 0 h |
| `it-umbria` | 0 | — | — | — | 0.0% | — | — |
| `it-valle-d-aosta` | 0 | — | — | — | 0.0% | — | — |
| `it-veneto` | 0 | — | — | — | 0.0% | — | — |
| **Italia** | **4347** | **6%** | **1%** | **7.80x** | | | |

Una regione senza celle bruciate non ha hit rate né FAR: non è «zero»,
è nessun incendio censito (perimetri EFFIS) nella finestra.

## Provenienza

| | |
|---|---|
| generato | 2026-11-12T21:25:34+00:00 |
| commit | `42d772137fbc3a64aaea44cddae040bd53b56ec6` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1` |
| flood | `flood-v1.3.0` |
| wildfire | `wildfire-v1.1.0` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_END` | `2025-12-31` |
| `LIMEN_BACKTEST_WILDFIRE_LEVEL` | `VeryHigh` |
| `LIMEN_BACKTEST_WILDFIRE_START` | `2025-01-01` |
| `LIMEN_BACKUP_DIR` | `<percorso locale>` |
| `LIMEN_DATA_ROOT` | `<percorso locale>` |
| `LIMEN_DOMINIO` | `localhost` |
| `LIMEN_IMAGE_PREFIX` | `ghcr.io/agent-engineering-studio/limen-` |
| `LIMEN_IMAGE_TAG` | `sha-e9e867e` |
| `LIMEN_IMPERVIOUSNESS_RASTER` | `<percorso locale>` |
| `LIMEN_MINIO_ROOT_USER` | `limen-admin` |
| `LIMEN_PROXY_BIND` | `127.0.0.1` |
| `LIMEN_REPORTS_DIR` | `<percorso locale>` |
