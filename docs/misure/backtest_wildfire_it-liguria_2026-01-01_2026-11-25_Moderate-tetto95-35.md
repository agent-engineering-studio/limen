# Limen backtest incendio — AOI `it-liguria`

Finestra: **2026-01-01 → 2026-11-25**
Generato: 2026-11-26T15:04:21.280370+00:00
Pioggia della catena: **modello**
Soglia di allerta: **Moderate**, orizzonte di preavviso **72 h**

- Celle bruciate (perimetri EFFIS nella finestra): **66**
- Celle con almeno un'allerta: **57**
- Hit: **57**, mancati: **9** (celle bruciate); falsi allarmi: **479845** giornate-cella

## Metriche §2.5

- **Hit rate**: 86.36%
- **Tasso di base**: 28.88% (quota di giornate in allerta a prescindere dagli incendi)
- **Discriminazione**: 2.99 volte il tasso di base
- **Carico meteo**: 7.97% delle giornate-nodo della stagione con FWI in fascia alta o oltre
- **Carico per cella**: 24.80% delle giornate-cella della stagione in allerta, su tutte le celle dell'AOI
- **Discriminazione spaziale**: 3.48 volte il carico per cella
- **Giorno peggiore**: 91.09% delle celle dell'AOI in allerta insieme (2026-08-13)
- **FAR per giornata-cella**: 99.96% delle giornate-cella in allerta su celle che non hanno bruciato nelle 72 h seguenti
- **Preavviso medio**: 55.6 h

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

- Per causa: meteo sotto la soglia 9.
- Per terra (CORINE): bosco e seminaturale 9.
- Per mese: 04: 9.

| Cella | Incendio | CORINE | FWI max | FWI norm. max | Terreno | Punteggio max | Causa |
|---|---|---|---:|---:|---:|---:|---|
| it-liguria|67|166 | 2026-04-01 | 311 | 4.6 | 0.13 | 0.74 | 0.10 | meteo sotto la soglia |
| it-liguria|67|167 | 2026-04-01 | 311 | 4.6 | 0.13 | 0.74 | 0.10 | meteo sotto la soglia |
| it-liguria|67|168 | 2026-04-01 | 311 | 4.6 | 0.13 | 0.76 | 0.10 | meteo sotto la soglia |
| it-liguria|68|166 | 2026-04-01 | 333 | 4.6 | 0.13 | 0.79 | 0.10 | meteo sotto la soglia |
| it-liguria|68|167 | 2026-04-01 | 311 | 4.6 | 0.13 | 0.74 | 0.10 | meteo sotto la soglia |
| it-liguria|68|168 | 2026-04-01 | 333 | 4.6 | 0.13 | 0.81 | 0.11 | meteo sotto la soglia |
| it-liguria|69|166 | 2026-04-01 | 311 | 4.6 | 0.13 | 0.75 | 0.10 | meteo sotto la soglia |
| it-liguria|69|167 | 2026-04-01 | 311 | 4.6 | 0.13 | 0.75 | 0.10 | meteo sotto la soglia |
| it-liguria|69|168 | 2026-04-01 | 311 | 4.6 | 0.13 | 0.76 | 0.10 | meteo sotto la soglia |

## Provenienza

| | |
|---|---|
| generato | 2026-11-26T15:04:21+00:00 |
| commit | `89882ad5b11450cec70d66f6832298a095e64b98` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1.1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_AOI` | `it-liguria` |
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
