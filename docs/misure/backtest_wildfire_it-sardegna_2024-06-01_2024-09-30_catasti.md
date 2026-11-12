# Limen backtest incendio — AOI `it-sardegna`

Finestra: **2024-06-01 → 2024-09-30**
Generato: 2026-11-12T16:20:46.181740+00:00
Pioggia della catena: **modello**
Soglia di allerta: **High**, orizzonte di preavviso **72 h**

- Celle bruciate (catasti regionali degli incendi nella finestra): **1202**
- Celle con almeno un'allerta: **714**
- Hit: **714**, mancati: **488** (celle bruciate); falsi allarmi: **1075784** giornate-cella

## Metriche §2.5

- **Hit rate**: 59.40%
- **Tasso di base**: 31.70% (quota di giornate in allerta a prescindere dagli incendi)
- **Discriminazione**: 1.87 volte il tasso di base
- **Carico meteo**: 45.02% delle giornate-nodo della stagione con FWI in fascia alta o oltre
- **Carico per cella**: 35.32% delle giornate-cella della stagione in allerta, su tutte le celle dell'AOI
- **Discriminazione spaziale**: 1.68 volte il carico per cella
- **Giorno peggiore**: 87.74% delle celle dell'AOI in allerta insieme (2024-07-21)
- **FAR per giornata-cella**: 99.82% delle giornate-cella in allerta su celle che non hanno bruciato nelle 72 h seguenti
- **Preavviso medio**: 55.2 h

> L'hit rate da solo non dice nulla: un modello che dichiara pericolo
> alto tutti i giorni d'estate lo massimizza senza discriminare. Il
> confronto con il tasso di base è ciò che separa la bravura dalla
> frequenza — sotto 1.0 il modello è peggio del caso.
> Hit rate e preavviso guardano le celle che hanno bruciato, nelle
> 72 h prima di ciascun incendio. Il FAR guarda **tutte** le
> celle dell'AOI per tutta la stagione: un'allerta è falsa se la sua cella
> non brucia nell'orizzonte di preavviso. Con i perimetri EFFIS, che
> censiscono gli incendi grandi, è alto per costruzione: si legge come
> quante allerte arrivano per ogni incendio vero, e si confronta fra
> varianti, non con lo zero.

## Provenienza

| | |
|---|---|
| generato | 2026-11-12T16:20:46+00:00 |
| commit | `07d02d0fa012961cf49144fd805bebb2691c4a58` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1` |
| flood | `flood-v1.3.0` |
| wildfire | `wildfire-v1.1.0` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_AOI` | `it-sardegna` |
| `LIMEN_BACKTEST_WILDFIRE_END` | `2024-09-30` |
| `LIMEN_BACKTEST_WILDFIRE_ETTARI` | `` |
| `LIMEN_BACKTEST_WILDFIRE_START` | `2024-06-01` |
| `LIMEN_BACKTEST_WILDFIRE_VERITA` | `catasti` |
| `LIMEN_BACKUP_DIR` | `<percorso locale>` |
| `LIMEN_DATA_ROOT` | `<percorso locale>` |
| `LIMEN_DOMINIO` | `localhost` |
| `LIMEN_IMAGE_PREFIX` | `ghcr.io/agent-engineering-studio/limen-` |
| `LIMEN_IMAGE_TAG` | `sha-e9e867e` |
| `LIMEN_IMPERVIOUSNESS_RASTER` | `<percorso locale>` |
| `LIMEN_MINIO_ROOT_USER` | `limen-admin` |
| `LIMEN_PROXY_BIND` | `127.0.0.1` |
| `LIMEN_REPORTS_DIR` | `<percorso locale>` |
