# Limen backtest incendio — AOI `it-basilicata`

Finestra: **2025-06-01 → 2025-09-30**
Generato: 2026-11-12T16:30:01.714424+00:00
Pioggia della catena: **modello**
Soglia di allerta: **High**, orizzonte di preavviso **72 h**

- Celle bruciate (catasti regionali degli incendi, incendi da 0 a 1 ha nella finestra): **74**
- Celle con almeno un'allerta: **48**
- Hit: **48**, mancati: **26** (celle bruciate); falsi allarmi: **574772** giornate-cella

## Metriche §2.5

- **Hit rate**: 64.86%
- **Tasso di base**: 40.31% (quota di giornate in allerta a prescindere dagli incendi)
- **Discriminazione**: 1.61 volte il tasso di base
- **Carico meteo**: 61.77% delle giornate-nodo della stagione con FWI in fascia alta o oltre
- **Carico per cella**: 45.52% delle giornate-cella della stagione in allerta, su tutte le celle dell'AOI
- **Discriminazione spaziale**: 1.43 volte il carico per cella
- **Giorno peggiore**: 92.56% delle celle dell'AOI in allerta insieme (2025-07-25)
- **FAR per giornata-cella**: 99.97% delle giornate-cella in allerta su celle che non hanno bruciato nelle 72 h seguenti
- **Preavviso medio**: 62.5 h

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
| generato | 2026-11-12T16:30:01+00:00 |
| commit | `b28e205ff30782984658f9fbc1ec83d63be348a6` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1` |
| flood | `flood-v1.3.0` |
| wildfire | `wildfire-v1.1.0` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_AOI` | `it-basilicata` |
| `LIMEN_BACKTEST_WILDFIRE_END` | `2025-09-30` |
| `LIMEN_BACKTEST_WILDFIRE_ETTARI` | `-1` |
| `LIMEN_BACKTEST_WILDFIRE_START` | `2025-06-01` |
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
