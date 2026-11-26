# I roghi agricoli anticipano gli incendi? `crop_burning_share` (#714)

Regioni: it-lombardia, it-piemonte, it-veneto, it-emilia-romagna, it-liguria, it-friuli-venezia-giulia, it-trentino-alto-adige, it-valle-d-aosta. La quota è ricalcolata con i soli fuochi VIIRS di vegetazione fino al 2023-12-31; bruciata è una cella coperta per almeno un quarto da perimetri EFFIS fra il 2024-01-01 e il 2026-12-31. Strati: nodo 0.25° e fascia di quota.

## Chi la quota la può vedere

Celle 124716, bruciate 470. Con almeno un giorno-incendio prima: 6980 celle, e fra le bruciate 135 su 470 (29%). Le altre non hanno una quota: nessuna feature fatta dai fuochi passati le vede.

Tasso di base: 0.019 fra le celle già bruciate, 0.003 fra le altre.

## Sulle celle già bruciate

- `crop_burning_share`: AUC stratificata 0.389 su 49 strati (sotto 0,5: più coltivo, **meno** incendi).
- giorni-incendio passati, per confronto: AUC stratificata 0.732 su 49 strati.
- mediana della quota: 0.011 sulle celle che bruciano, 0.092 sulle altre.

### Osservate/attese per classe di quota

| classe | celle | bruciate | attese | O/A |
|---|---:|---:|---:|---:|
| [0, 0.02436) | 2792 | 71 | 55.1 | 1.29 |
| [0.02436, 0.214) | 1396 | 27 | 26.4 | 1.02 |
| [0.214, 0.6541) | 1396 | 12 | 22.7 | 0.53 |
| [0.6541, +inf) | 1396 | 25 | 30.8 | 0.81 |

### A parità di fuoco

- giorni-incendio 1-2: AUC della quota 0.340.
- giorni-incendio 3 o più: AUC della quota 0.498.

## Regione per regione

| regione | celle già bruciate | bruciate dopo | AUC della quota |
|---|---:|---:|---:|
| it-lombardia | 1840 | 35 | 0.541 |
| it-piemonte | 1773 | 30 | 0.268 |
| it-veneto | 1086 | 18 | 0.251 |
| it-emilia-romagna | 1380 | 30 | 0.679 |
| it-liguria | 448 | 15 | 0.434 |
| it-friuli-venezia-giulia | 269 | 7 | 0.311 |
| it-trentino-alto-adige | 152 | 0 | — |
| it-valle-d-aosta | 32 | 0 | — |

AUC non stratificata per regione; «—» dove non ci sono celle bruciate. EFFIS mappa gli incendi da circa 30 ha: la misura non dice niente sui piccoli abbruciamenti.

## Provenienza

| | |
|---|---|
| generato | 2026-11-26T12:47:00+00:00 |
| commit | `ac507899c1b710d9ae9e0aa5fea3ca3c2319d147` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1.1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen misura-coltivi` |
| `LIMEN_BACKUP_DIR` | `<percorso locale>` |
| `LIMEN_DATA_ROOT` | `<percorso locale>` |
| `LIMEN_DOMINIO` | `localhost` |
| `LIMEN_IMAGE_PREFIX` | `ghcr.io/agent-engineering-studio/limen-` |
| `LIMEN_IMAGE_TAG` | `sha-eda9890` |
| `LIMEN_IMPERVIOUSNESS_RASTER` | `<percorso locale>` |
| `LIMEN_PROXY_BIND` | `127.0.0.1` |
| `LIMEN_REPORTS_DIR` | `<percorso locale>` |
