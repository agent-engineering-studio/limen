# Limen backtest incendio — AOI `it-trentino-alto-adige`

Finestra: **2026-01-01 → 2026-11-25**
Generato: 2026-11-26T15:05:19.312064+00:00
Pioggia della catena: **modello**
Soglia di allerta: **Moderate**, orizzonte di preavviso **72 h**

- Celle bruciate (perimetri EFFIS nella finestra): **12**
- Celle con almeno un'allerta: **6**
- Hit: **6**, mancati: **6** (celle bruciate); falsi allarmi: **511029** giornate-cella

## Metriche §2.5

- **Hit rate**: 50.00%
- **Tasso di base**: 7.88% (quota di giornate in allerta a prescindere dagli incendi)
- **Discriminazione**: 6.35 volte il tasso di base
- **Carico meteo**: 3.95% delle giornate-nodo della stagione con FWI in fascia alta o oltre
- **Carico per cella**: 11.03% delle giornate-cella della stagione in allerta, su tutte le celle dell'AOI
- **Discriminazione spaziale**: 4.53 volte il carico per cella
- **Giorno peggiore**: 70.59% delle celle dell'AOI in allerta insieme (2026-07-09)
- **FAR per giornata-cella**: 100.00% delle giornate-cella in allerta su celle che non hanno bruciato nelle 72 h seguenti
- **Preavviso medio**: 72.0 h

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

- Per causa: meteo sotto la soglia 6.
- Per terra (CORINE): bosco e seminaturale 5, agricola 1.
- Per mese: 07: 6.

| Cella | Incendio | CORINE | FWI max | FWI norm. max | Terreno | Punteggio max | Causa |
|---|---|---|---:|---:|---:|---:|---|
| it-trentino-alto-adige|68|23 | 2026-07-03 | 312 | 1.1 | 0.03 | 0.94 | 0.03 | meteo sotto la soglia |
| it-trentino-alto-adige|68|24 | 2026-07-03 | 312 | 1.1 | 0.03 | 0.98 | 0.03 | meteo sotto la soglia |
| it-trentino-alto-adige|69|23 | 2026-07-03 | 312 | 1.1 | 0.03 | 0.98 | 0.03 | meteo sotto la soglia |
| it-trentino-alto-adige|69|24 | 2026-07-03 | 231 | 1.1 | 0.03 | 0.75 | 0.02 | meteo sotto la soglia |
| it-trentino-alto-adige|70|23 | 2026-07-03 | 312 | 1.1 | 0.03 | 0.98 | 0.03 | meteo sotto la soglia |
| it-trentino-alto-adige|70|24 | 2026-07-03 | 312 | 1.1 | 0.03 | 0.98 | 0.03 | meteo sotto la soglia |

## Provenienza

| | |
|---|---|
| generato | 2026-11-26T15:05:19+00:00 |
| commit | `89882ad5b11450cec70d66f6832298a095e64b98` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1.1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_AOI` | `it-trentino-alto-adige` |
| `LIMEN_BACKTEST_WILDFIRE_END` | `2026-11-25` |
| `LIMEN_BACKTEST_WILDFIRE_LEVEL` | `Moderate` |
| `LIMEN_BACKTEST_WILDFIRE_START` | `2026-01-01` |
| `LIMEN_BACKTEST_WILDFIRE_TETTO` | `95:35:6-9` |
| `LIMEN_BACKUP_DIR` | `<percorso locale>` |
| `LIMEN_DATA_ROOT` | `<percorso locale>` |
| `LIMEN_DOMINIO` | `localhost` |
| `LIMEN_IMAGE_PREFIX` | `ghcr.io/agent-engineering-studio/limen-` |
| `LIMEN_IMAGE_TAG` | `sha-ecddbd8` |
| `LIMEN_IMPERVIOUSNESS_RASTER` | `<percorso locale>` |
| `LIMEN_PROXY_BIND` | `127.0.0.1` |
| `LIMEN_REPORTS_DIR` | `<percorso locale>` |
