# Limen backtest incendio — AOI `it-calabria`

Finestra: **2024-06-01 → 2024-09-30**
Generato: 2026-11-11T17:27:14.678251+00:00
Pioggia della catena: **modello**
Soglia di allerta: **High**, orizzonte di preavviso **72 h**

- Celle bruciate (perimetri EFFIS nella finestra): **391**
- Celle con almeno un'allerta: **224**
- Hit: **224**, mancati: **167** (celle bruciate); falsi allarmi: **366242** giornate-cella

## Metriche §2.5

- **Hit rate**: 57.29%
- **Tasso di base**: 24.66% (quota di giornate in allerta a prescindere dagli incendi)
- **Discriminazione**: 2.32 volte il tasso di base
- **Carico meteo**: 30.15% delle giornate-nodo della stagione con FWI in fascia alta o oltre
- **Carico per cella**: 19.28% delle giornate-cella della stagione in allerta, su tutte le celle dell'AOI
- **Discriminazione spaziale**: 2.97 volte il carico per cella
- **Giorno peggiore**: 67.43% delle celle dell'AOI in allerta insieme (2024-08-03)
- **FAR per giornata-cella**: 99.82% delle giornate-cella in allerta su celle che non hanno bruciato nelle 72 h seguenti
- **Preavviso medio**: 54.0 h

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
| generato | 2026-11-11T17:27:14+00:00 |
| commit | `c3a0bc6ca4085b4d1e13e3a9e93fb233f58508fa` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1` |
| flood | `flood-v1.3.0` |
| wildfire | `wildfire-v1.1.0` |
| comando | `limen backtest-wildfire` |
| `FORECAST__ENABLED` | `true` |
| `FORECAST__HORIZON_HOURS` | `48` |
| `FORECAST__HOURS_UTC` | `[2,8,14,20]` |
| `FORECAST__MINUTE` | `50` |
| `FORECAST__MIN_LEVEL` | `High` |
| `LIMEN_BACKTEST_WILDFIRE_AOI` | `it-calabria` |
| `LIMEN_BACKTEST_WILDFIRE_END` | `2024-09-30` |
| `LIMEN_BACKTEST_WILDFIRE_START` | `2024-06-01` |
| `LIMEN_DATA_DIR` | `<percorso locale>` |
| `LIMEN_DATA_ROOT` | `<percorso locale>` |
| `LIMEN_DEM_RASTER` | `` |
| `LIMEN_REPORTS_DIR` | `<percorso locale>` |
| `SCORING__MLFLOW_ARTIFACT_ROOT` | `file:///var/lib/limen/mlruns` |
| `SCORING__MLFLOW_TRACKING_URI` | `postgresql://<credenziali>@postgres:5432/mlflow` |
| `SCORING__MODE` | `champion_only` |
