# Limen backtest incendio — AOI `it-puglia`

Finestra: **2025-06-01 → 2025-09-30**
Generato: 2026-11-12T13:51:34.661262+00:00
Pioggia della catena: **modello**
Soglia di allerta: **High**, orizzonte di preavviso **72 h**

- Celle bruciate (perimetri EFFIS nella finestra): **836**
- Celle con almeno un'allerta: **715**
- Hit: **715**, mancati: **121** (celle bruciate); falsi allarmi: **865205** giornate-cella

## Metriche §2.5

- **Hit rate**: 85.53%
- **Tasso di base**: 36.87% (quota di giornate in allerta a prescindere dagli incendi)
- **Discriminazione**: 2.32 volte il tasso di base
- **Carico meteo**: 50.95% delle giornate-nodo della stagione con FWI in fascia alta o oltre
- **Carico per cella**: 35.41% delle giornate-cella della stagione in allerta, su tutte le celle dell'AOI
- **Discriminazione spaziale**: 2.42 volte il carico per cella
- **Giorno peggiore**: 89.52% delle celle dell'AOI in allerta insieme (2025-06-28)
- **FAR per giornata-cella**: 99.76% delle giornate-cella in allerta su celle che non hanno bruciato nelle 72 h seguenti
- **Preavviso medio**: 57.9 h

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
| generato | 2026-11-12T13:51:34+00:00 |
| commit | `1325f0e1ae6e14ec06e4053b2e5b61b64a9aa55a` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1` |
| flood | `flood-v1.3.0` |
| wildfire | `wildfire-v1.1.0` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_AOI` | `it-puglia` |
| `LIMEN_BACKTEST_WILDFIRE_END` | `2025-09-30` |
| `LIMEN_BACKTEST_WILDFIRE_START` | `2025-06-01` |
| `LIMEN_BACKUP_DIR` | `<percorso locale>` |
| `LIMEN_DATA_ROOT` | `<percorso locale>` |
| `LIMEN_DOMINIO` | `localhost` |
| `LIMEN_IMAGE_PREFIX` | `ghcr.io/agent-engineering-studio/limen-` |
| `LIMEN_IMAGE_TAG` | `sha-e9e867e` |
| `LIMEN_IMPERVIOUSNESS_RASTER` | `<percorso locale>` |
| `LIMEN_MINIO_ROOT_USER` | `limen-admin` |
| `LIMEN_PROXY_BIND` | `127.0.0.1` |
| `LIMEN_REPORTS_DIR` | `<percorso locale>` |
