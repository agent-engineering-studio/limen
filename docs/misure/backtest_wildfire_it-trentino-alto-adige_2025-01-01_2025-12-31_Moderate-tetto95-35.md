# Limen backtest incendio — AOI `it-trentino-alto-adige`

Finestra: **2025-01-01 → 2025-12-31**
Generato: 2026-11-26T14:59:15.291524+00:00
Pioggia della catena: **modello**
Soglia di allerta: **Moderate**, orizzonte di preavviso **72 h**

- Celle bruciate (perimetri EFFIS nella finestra): **15**
- Celle con almeno un'allerta: **0**
- Hit: **0**, mancati: **15** (celle bruciate); falsi allarmi: **179109** giornate-cella

## Metriche §2.5

- **Hit rate**: 0.00%
- **Tasso di base**: 1.88% (quota di giornate in allerta a prescindere dagli incendi)
- **Discriminazione**: 0.00 volte il tasso di base
- **Carico meteo**: 0.74% delle giornate-nodo della stagione con FWI in fascia alta o oltre
- **Carico per cella**: 3.49% delle giornate-cella della stagione in allerta, su tutte le celle dell'AOI
- **Discriminazione spaziale**: 0.00 volte il carico per cella
- **Giorno peggiore**: 49.96% delle celle dell'AOI in allerta insieme (2025-08-13)
- **FAR per giornata-cella**: 100.00% delle giornate-cella in allerta su celle che non hanno bruciato nelle 72 h seguenti
- **Preavviso medio**: 0.0 h

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

- Per causa: meteo sotto la soglia 15.
- Per terra (CORINE): bosco e seminaturale 13, agricola 2.
- Per mese: 03: 7, 04: 8.

| Cella | Incendio | CORINE | FWI max | FWI norm. max | Terreno | Punteggio max | Causa |
|---|---|---|---:|---:|---:|---:|---|
| it-trentino-alto-adige|105|36 | 2025-03-06 | 324 | 0.5 | 0.01 | 0.87 | 0.01 | meteo sotto la soglia |
| it-trentino-alto-adige|105|37 | 2025-03-06 | 222 | 0.6 | 0.02 | 0.58 | 0.01 | meteo sotto la soglia |
| it-trentino-alto-adige|106|35 | 2025-03-06 | 312 | 0.5 | 0.01 | 0.98 | 0.01 | meteo sotto la soglia |
| it-trentino-alto-adige|106|36 | 2025-03-06 | 324 | 0.5 | 0.01 | 0.91 | 0.01 | meteo sotto la soglia |
| it-trentino-alto-adige|106|37 | 2025-03-06 | 312 | 0.3 | 0.01 | 0.98 | 0.01 | meteo sotto la soglia |
| it-trentino-alto-adige|107|36 | 2025-03-06 | 312 | 0.5 | 0.01 | 0.96 | 0.01 | meteo sotto la soglia |
| it-trentino-alto-adige|107|37 | 2025-03-06 | 312 | 0.3 | 0.01 | 0.98 | 0.01 | meteo sotto la soglia |
| it-trentino-alto-adige|102|12 | 2025-04-10 | 231 | 0.7 | 0.02 | 0.76 | 0.02 | meteo sotto la soglia |
| it-trentino-alto-adige|102|13 | 2025-04-10 | 312 | 0.7 | 0.02 | 0.97 | 0.02 | meteo sotto la soglia |
| it-trentino-alto-adige|103|12 | 2025-04-10 | 324 | 0.7 | 0.02 | 0.90 | 0.02 | meteo sotto la soglia |
| it-trentino-alto-adige|103|13 | 2025-04-10 | 324 | 0.7 | 0.02 | 0.91 | 0.02 | meteo sotto la soglia |
| it-trentino-alto-adige|104|11 | 2025-04-10 | 312 | 0.7 | 0.02 | 0.96 | 0.02 | meteo sotto la soglia |
| it-trentino-alto-adige|104|12 | 2025-04-10 | 312 | 0.7 | 0.02 | 0.96 | 0.02 | meteo sotto la soglia |
| it-trentino-alto-adige|104|13 | 2025-04-10 | 312 | 0.7 | 0.02 | 0.97 | 0.02 | meteo sotto la soglia |
| it-trentino-alto-adige|105|12 | 2025-04-10 | 312 | 4.6 | 0.13 | 0.98 | 0.13 | meteo sotto la soglia |

## Provenienza

| | |
|---|---|
| generato | 2026-11-26T14:59:15+00:00 |
| commit | `89882ad5b11450cec70d66f6832298a095e64b98` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1.1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_AOI` | `it-trentino-alto-adige` |
| `LIMEN_BACKTEST_WILDFIRE_END` | `2025-12-31` |
| `LIMEN_BACKTEST_WILDFIRE_LEVEL` | `Moderate` |
| `LIMEN_BACKTEST_WILDFIRE_START` | `2025-01-01` |
| `LIMEN_BACKTEST_WILDFIRE_TETTO` | `95:35:6-9` |
| `LIMEN_BACKUP_DIR` | `<percorso locale>` |
| `LIMEN_DATA_ROOT` | `<percorso locale>` |
| `LIMEN_DOMINIO` | `localhost` |
| `LIMEN_IMAGE_PREFIX` | `ghcr.io/agent-engineering-studio/limen-` |
| `LIMEN_IMAGE_TAG` | `sha-ecddbd8` |
| `LIMEN_IMPERVIOUSNESS_RASTER` | `<percorso locale>` |
| `LIMEN_PROXY_BIND` | `127.0.0.1` |
| `LIMEN_REPORTS_DIR` | `<percorso locale>` |
