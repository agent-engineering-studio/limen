# Limen backtest incendio — Italia

Finestra: **2025-01-01 → 2025-12-31**; soglia di allerta **Moderate**, orizzonte di preavviso **72 h**; verità: perimetri EFFIS. Il dettaglio di ogni regione è nel suo report.

| AOI | celle bruciate | hit rate | tasso di base | discriminazione | carico per cella | FAR (giornate-cella) | preavviso |
|---|---:|---:|---:|---:|---:|---:|---:|
| `it-abruzzo` | 48 | 88% | 26% | 3.35x | 19.3% | 100.0% | 63 h |
| `it-basilicata` | 339 | 98% | 30% | 3.27x | 30.5% | 99.9% | 70 h |
| `it-calabria` | 673 | 88% | 26% | 3.40x | 24.2% | 99.8% | 66 h |
| `it-campania` | 221 | 89% | 20% | 4.45x | 18.7% | 99.9% | 64 h |
| `it-emilia-romagna` | 22 | 18% | 11% | 1.60x | 10.7% | 100.0% | 72 h |
| `it-friuli-venezia-giulia` | 0 | — | — | — | 0.0% | — | — |
| `it-lazio` | 142 | 83% | 20% | 4.17x | 17.9% | 100.0% | 63 h |
| `it-liguria` | 0 | — | — | — | 0.0% | — | — |
| `it-lombardia` | 11 | 0% | 1% | 0.00x | 3.0% | 100.0% | 0 h |
| `it-marche` | 4 | 0% | 21% | 0.00x | 20.2% | 100.0% | 0 h |
| `it-molise` | 78 | 100% | 24% | 4.18x | 22.6% | 99.9% | 68 h |
| `it-piemonte` | 12 | 33% | 3% | 9.80x | 4.7% | 100.0% | 72 h |
| `it-puglia` | 872 | 95% | 27% | 3.50x | 26.3% | 99.8% | 67 h |
| `it-sardegna` | 182 | 93% | 34% | 2.75x | 32.2% | 100.0% | 67 h |
| `it-sicilia` | 1699 | 91% | 28% | 3.21x | 26.2% | 99.8% | 67 h |
| `it-toscana` | 29 | 100% | 19% | 5.27x | 17.2% | 100.0% | 70 h |
| `it-trentino-alto-adige` | 15 | 0% | 2% | 0.00x | 3.5% | 100.0% | 0 h |
| `it-umbria` | 0 | — | — | — | 0.0% | — | — |
| `it-valle-d-aosta` | 0 | — | — | — | 0.0% | — | — |
| `it-veneto` | 0 | — | — | — | 0.0% | — | — |
| **Italia** | **4347** | **91%** | **27%** | **3.37x** | | | |

Una regione senza celle bruciate non ha hit rate né FAR: non è «zero»,
è nessun incendio censito (perimetri EFFIS) nella finestra.

## Provenienza

| | |
|---|---|
| generato | 2026-11-19T21:01:18+00:00 |
| commit | `b2f7b2157a4f9b7cc42ee0786f4ee443ff871bc6` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_CANCELLO` | `0.3` |
| `LIMEN_BACKTEST_WILDFIRE_END` | `2025-12-31` |
| `LIMEN_BACKTEST_WILDFIRE_LEVEL` | `Moderate` |
| `LIMEN_BACKTEST_WILDFIRE_START` | `2025-01-01` |
| `LIMEN_BACKTEST_WILDFIRE_TETTO` | `95:35:6-9` |
| `LIMEN_BACKUP_DIR` | `<percorso locale>` |
| `LIMEN_DATA_ROOT` | `<percorso locale>` |
| `LIMEN_DOMINIO` | `localhost` |
| `LIMEN_IMAGE_PREFIX` | `ghcr.io/agent-engineering-studio/limen-` |
| `LIMEN_IMAGE_TAG` | `sha-9b96afc` |
| `LIMEN_IMPERVIOUSNESS_RASTER` | `<percorso locale>` |
| `LIMEN_PROXY_BIND` | `127.0.0.1` |
| `LIMEN_REPORTS_DIR` | `<percorso locale>` |
