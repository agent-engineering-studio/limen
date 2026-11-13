# Limen backtest incendio — Italia

Finestra: **2026-01-01 → 2026-11-10**; soglia di allerta **High**, orizzonte di preavviso **72 h**; verità: perimetri EFFIS. Il dettaglio di ogni regione è nel suo report.

| AOI | celle bruciate | hit rate | tasso di base | discriminazione | carico per cella | FAR (giornate-cella) | preavviso |
|---|---:|---:|---:|---:|---:|---:|---:|
| `it-abruzzo` | 238 | 70% | 15% | 4.69x | 10.3% | 99.8% | 61 h |
| `it-basilicata` | 581 | 85% | 20% | 4.14x | 20.7% | 99.8% | 64 h |
| `it-calabria` | 1044 | 56% | 12% | 4.67x | 10.4% | 99.7% | 54 h |
| `it-campania` | 418 | 49% | 11% | 4.51x | 10.6% | 99.9% | 42 h |
| `it-emilia-romagna` | 100 | 18% | 2% | 8.75x | 2.1% | 100.0% | 27 h |
| `it-friuli-venezia-giulia` | 78 | 0% | 0% | 0.00x | 0.6% | 100.0% | 0 h |
| `it-lazio` | 416 | 41% | 9% | 4.67x | 7.9% | 99.9% | 50 h |
| `it-liguria` | 66 | 9% | 4% | 2.05x | 2.8% | 100.0% | 36 h |
| `it-lombardia` | 109 | 3% | 1% | 4.24x | 0.6% | 100.0% | 56 h |
| `it-marche` | 9 | 100% | 11% | 9.03x | 8.4% | 100.0% | 72 h |
| `it-molise` | 102 | 69% | 16% | 4.30x | 15.2% | 99.9% | 66 h |
| `it-piemonte` | 279 | 11% | 2% | 4.62x | 1.3% | 100.0% | 40 h |
| `it-puglia` | 2327 | 69% | 17% | 4.06x | 15.6% | 99.6% | 54 h |
| `it-sardegna` | 418 | 68% | 17% | 4.04x | 24.4% | 100.0% | 52 h |
| `it-sicilia` | 3799 | 69% | 15% | 4.75x | 13.1% | 99.2% | 62 h |
| `it-toscana` | 78 | 33% | 6% | 5.40x | 8.5% | 100.0% | 30 h |
| `it-trentino-alto-adige` | 12 | 0% | 0% | 0.00x | 1.7% | 100.0% | 0 h |
| `it-umbria` | 21 | 33% | 7% | 4.54x | 10.2% | 100.0% | 72 h |
| `it-valle-d-aosta` | 6 | 0% | 11% | 0.00x | 4.6% | 100.0% | 0 h |
| `it-veneto` | 59 | 0% | 0% | 0.00x | 0.4% | 100.0% | 0 h |
| **Italia** | **10160** | **62%** | **14%** | **4.45x** | | | |

Una regione senza celle bruciate non ha hit rate né FAR: non è «zero»,
è nessun incendio censito (perimetri EFFIS) nella finestra.

## Provenienza

| | |
|---|---|
| generato | 2026-11-12T20:08:22+00:00 |
| commit | `42d772137fbc3a64aaea44cddae040bd53b56ec6` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1` |
| flood | `flood-v1.3.0` |
| wildfire | `wildfire-v1.1.0` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_END` | `2026-11-10` |
| `LIMEN_BACKTEST_WILDFIRE_LEVEL` | `High` |
| `LIMEN_BACKTEST_WILDFIRE_START` | `2026-01-01` |
| `LIMEN_BACKUP_DIR` | `<percorso locale>` |
| `LIMEN_DATA_ROOT` | `<percorso locale>` |
| `LIMEN_DOMINIO` | `localhost` |
| `LIMEN_IMAGE_PREFIX` | `ghcr.io/agent-engineering-studio/limen-` |
| `LIMEN_IMAGE_TAG` | `sha-e9e867e` |
| `LIMEN_IMPERVIOUSNESS_RASTER` | `<percorso locale>` |
| `LIMEN_MINIO_ROOT_USER` | `limen-admin` |
| `LIMEN_PROXY_BIND` | `127.0.0.1` |
| `LIMEN_REPORTS_DIR` | `<percorso locale>` |
