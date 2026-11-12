# Limen backtest incendio — AOI `it-basilicata`

Finestra: **2024-06-01 → 2024-09-30**
Generato: 2026-11-12T16:39:37.117777+00:00
Pioggia della catena: **modello**
Soglia di allerta: **High**, orizzonte di preavviso **72 h**

- Celle bruciate (catasti regionali degli incendi, incendi da 1 a 10 ha nella finestra): **156**
- Celle con almeno un'allerta: **121**
- Hit: **121**, mancati: **35** (celle bruciate); falsi allarmi: **394727** giornate-cella

## Metriche §2.5

- **Hit rate**: 77.56%
- **Tasso di base**: 31.21% (quota di giornate in allerta a prescindere dagli incendi)
- **Discriminazione**: 2.49 volte il tasso di base
- **Carico meteo**: 48.32% delle giornate-nodo della stagione con FWI in fascia alta o oltre
- **Carico per cella**: 31.28% delle giornate-cella della stagione in allerta, su tutte le celle dell'AOI
- **Discriminazione spaziale**: 2.48 volte il carico per cella
- **Giorno peggiore**: 90.85% delle celle dell'AOI in allerta insieme (2024-08-03)
- **FAR per giornata-cella**: 99.91% delle giornate-cella in allerta su celle che non hanno bruciato nelle 72 h seguenti
- **Preavviso medio**: 54.9 h

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
| generato | 2026-11-12T16:39:37+00:00 |
| commit | `b28e205ff30782984658f9fbc1ec83d63be348a6` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1` |
| flood | `flood-v1.3.0` |
| wildfire | `wildfire-v1.1.0` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_AOI` | `it-basilicata` |
| `LIMEN_BACKTEST_WILDFIRE_END` | `2024-09-30` |
| `LIMEN_BACKTEST_WILDFIRE_ETTARI` | `1-10` |
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
