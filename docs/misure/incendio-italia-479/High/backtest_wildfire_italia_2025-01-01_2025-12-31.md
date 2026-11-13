# Limen backtest incendio — Italia

Finestra: **2025-01-01 → 2025-12-31**; soglia di allerta **High**, orizzonte di preavviso **72 h**; verità: perimetri EFFIS. Il dettaglio di ogni regione è nel suo report.

| AOI | celle bruciate | hit rate | tasso di base | discriminazione | carico per cella | FAR (giornate-cella) | preavviso |
|---|---:|---:|---:|---:|---:|---:|---:|
| `it-abruzzo` | 48 | 38% | 7% | 5.14x | 3.9% | 100.0% | 44 h |
| `it-basilicata` | 339 | 80% | 16% | 5.05x | 15.7% | 99.9% | 55 h |
| `it-calabria` | 673 | 55% | 9% | 6.34x | 8.9% | 99.8% | 51 h |
| `it-campania` | 221 | 61% | 6% | 10.40x | 4.4% | 99.8% | 47 h |
| `it-emilia-romagna` | 22 | 14% | 1% | 11.90x | 0.5% | 100.0% | 72 h |
| `it-friuli-venezia-giulia` | 0 | — | — | — | 0.0% | — | — |
| `it-lazio` | 142 | 36% | 4% | 9.01x | 3.6% | 99.9% | 54 h |
| `it-liguria` | 0 | — | — | — | 0.0% | — | — |
| `it-lombardia` | 11 | 0% | 0% | 0.00x | 0.0% | 100.0% | 0 h |
| `it-marche` | 4 | 0% | 1% | 0.00x | 2.9% | 100.0% | 0 h |
| `it-molise` | 78 | 47% | 5% | 8.90x | 5.4% | 99.9% | 45 h |
| `it-piemonte` | 12 | 8% | 0% | 36.50x | 0.1% | 100.0% | 72 h |
| `it-puglia` | 872 | 83% | 13% | 6.56x | 12.1% | 99.8% | 59 h |
| `it-sardegna` | 182 | 83% | 19% | 4.37x | 18.8% | 100.0% | 59 h |
| `it-sicilia` | 1699 | 69% | 15% | 4.57x | 11.8% | 99.7% | 58 h |
| `it-toscana` | 29 | 52% | 2% | 29.59x | 2.9% | 100.0% | 62 h |
| `it-trentino-alto-adige` | 15 | 0% | 0% | 0.00x | 0.2% | 100.0% | 0 h |
| `it-umbria` | 0 | — | — | — | 0.0% | — | — |
| `it-valle-d-aosta` | 0 | — | — | — | 0.0% | — | — |
| `it-veneto` | 0 | — | — | — | 0.0% | — | — |
| **Italia** | **4347** | **68%** | **12%** | **5.46x** | | | |

Una regione senza celle bruciate non ha hit rate né FAR: non è «zero»,
è nessun incendio censito (perimetri EFFIS) nella finestra.

## Provenienza

| | |
|---|---|
| generato | 2026-11-12T19:28:13+00:00 |
| commit | `42d772137fbc3a64aaea44cddae040bd53b56ec6` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1` |
| flood | `flood-v1.3.0` |
| wildfire | `wildfire-v1.1.0` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_END` | `2025-12-31` |
| `LIMEN_BACKTEST_WILDFIRE_LEVEL` | `High` |
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
