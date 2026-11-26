# Limen backtest incendio — AOI `it-liguria`

Finestra: **2026-01-01 → 2026-11-25**
Generato: 2026-11-26T13:36:10.210775+00:00
Pioggia della catena: **modello**
Soglia di allerta: **Moderate**, orizzonte di preavviso **72 h**

- Celle bruciate (perimetri EFFIS nella finestra): **66**
- Celle con almeno un'allerta: **54**
- Hit: **54**, mancati: **12** (celle bruciate); falsi allarmi: **298604** giornate-cella

## Metriche §2.5

- **Hit rate**: 81.82%
- **Tasso di base**: 19.15% (quota di giornate in allerta a prescindere dagli incendi)
- **Discriminazione**: 4.27 volte il tasso di base
- **Carico meteo**: 7.97% delle giornate-nodo della stagione con FWI in fascia alta o oltre
- **Carico per cella**: 15.43% delle giornate-cella della stagione in allerta, su tutte le celle dell'AOI
- **Discriminazione spaziale**: 5.30 volte il carico per cella
- **Giorno peggiore**: 86.78% delle celle dell'AOI in allerta insieme (2026-08-04)
- **FAR per giornata-cella**: 99.95% delle giornate-cella in allerta su celle che non hanno bruciato nelle 72 h seguenti
- **Preavviso medio**: 49.3 h

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

## Mancati, con la causa

Soglia del livello: punteggio 0.24. Il punteggio è FWI normalizzato per terreno: **meteo sotto la soglia** se l'FWI non ci arrivava neanche col terreno pieno, **terreno sotto la soglia** se ci arrivava e combustibile e pendenza l'hanno tenuto sotto, **cancello degli avvisi** se il livello c'era e la predisposizione no.

- Per causa: meteo sotto la soglia 9, terreno sotto la soglia 3.
- Per terra (CORINE): bosco e seminaturale 9, agricola 3.
- Per mese: 04: 9, 07: 1, 10: 2.

| Cella | Incendio | CORINE | FWI max | FWI norm. max | Terreno | Punteggio max | Causa |
|---|---|---|---:|---:|---:|---:|---|
| it-liguria|67|166 | 2026-04-01 | 311 | 4.6 | 0.09 | 0.74 | 0.07 | meteo sotto la soglia |
| it-liguria|67|167 | 2026-04-01 | 311 | 4.6 | 0.09 | 0.74 | 0.07 | meteo sotto la soglia |
| it-liguria|67|168 | 2026-04-01 | 311 | 4.6 | 0.09 | 0.76 | 0.07 | meteo sotto la soglia |
| it-liguria|68|166 | 2026-04-01 | 333 | 4.6 | 0.09 | 0.79 | 0.07 | meteo sotto la soglia |
| it-liguria|68|167 | 2026-04-01 | 311 | 4.6 | 0.09 | 0.74 | 0.07 | meteo sotto la soglia |
| it-liguria|68|168 | 2026-04-01 | 333 | 4.6 | 0.09 | 0.81 | 0.08 | meteo sotto la soglia |
| it-liguria|69|166 | 2026-04-01 | 311 | 4.6 | 0.09 | 0.75 | 0.07 | meteo sotto la soglia |
| it-liguria|69|167 | 2026-04-01 | 311 | 4.6 | 0.09 | 0.75 | 0.07 | meteo sotto la soglia |
| it-liguria|69|168 | 2026-04-01 | 311 | 4.6 | 0.09 | 0.76 | 0.07 | meteo sotto la soglia |
| it-liguria|8|18 | 2026-07-18 | 243 | 15.5 | 0.31 | 0.55 | 0.17 | terreno sotto la soglia |
| it-liguria|71|104 | 2026-10-03 | 243 | 19.7 | 0.39 | 0.58 | 0.23 | terreno sotto la soglia |
| it-liguria|71|105 | 2026-10-03 | 243 | 19.7 | 0.39 | 0.57 | 0.22 | terreno sotto la soglia |

## Provenienza

| | |
|---|---|
| generato | 2026-11-26T13:36:10+00:00 |
| commit | `626506428402e7df05320c5296a6e9009362d538` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1.1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_AOI` | `it-liguria` |
| `LIMEN_BACKTEST_WILDFIRE_END` | `2026-11-25` |
| `LIMEN_BACKTEST_WILDFIRE_LEVEL` | `Moderate` |
| `LIMEN_BACKTEST_WILDFIRE_START` | `2026-01-01` |
| `LIMEN_BACKUP_DIR` | `<percorso locale>` |
| `LIMEN_DATA_ROOT` | `<percorso locale>` |
| `LIMEN_DOMINIO` | `localhost` |
| `LIMEN_IMAGE_PREFIX` | `ghcr.io/agent-engineering-studio/limen-` |
| `LIMEN_IMAGE_TAG` | `sha-ecddbd8` |
| `LIMEN_IMPERVIOUSNESS_RASTER` | `<percorso locale>` |
| `LIMEN_PROXY_BIND` | `127.0.0.1` |
| `LIMEN_REPORTS_DIR` | `<percorso locale>` |
