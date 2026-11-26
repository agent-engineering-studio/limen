# Limen backtest incendio — AOI `it-friuli-venezia-giulia`

Finestra: **2026-01-01 → 2026-11-25**
Generato: 2026-11-26T13:36:30.208071+00:00
Pioggia della catena: **modello**
Soglia di allerta: **Moderate**, orizzonte di preavviso **72 h**

- Celle bruciate (perimetri EFFIS nella finestra): **78**
- Celle con almeno un'allerta: **56**
- Hit: **56**, mancati: **22** (celle bruciate); falsi allarmi: **130625** giornate-cella

## Metriche §2.5

- **Hit rate**: 71.79%
- **Tasso di base**: 4.22% (quota di giornate in allerta a prescindere dagli incendi)
- **Discriminazione**: 17.01 volte il tasso di base
- **Carico meteo**: 6.19% delle giornate-nodo della stagione con FWI in fascia alta o oltre
- **Carico per cella**: 4.80% delle giornate-cella della stagione in allerta, su tutte le celle dell'AOI
- **Discriminazione spaziale**: 14.97 volte il carico per cella
- **Giorno peggiore**: 79.68% delle celle dell'AOI in allerta insieme (2026-08-04)
- **FAR per giornata-cella**: 99.94% delle giornate-cella in allerta su celle che non hanno bruciato nelle 72 h seguenti
- **Preavviso medio**: 45.9 h

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

- Per causa: meteo sotto la soglia 12, terreno sotto la soglia 10.
- Per terra (CORINE): agricola 9, bosco e seminaturale 9, artificiale 4.
- Per mese: 06: 6, 08: 16.

| Cella | Incendio | CORINE | FWI max | FWI norm. max | Terreno | Punteggio max | Causa |
|---|---|---|---:|---:|---:|---:|---|
| it-friuli-venezia-giulia|68|57 | 2026-06-06 | 211 | 0.4 | 0.01 | 0.46 | 0.00 | meteo sotto la soglia |
| it-friuli-venezia-giulia|68|58 | 2026-06-06 | 121 | 0.4 | 0.01 | 0.32 | 0.00 | meteo sotto la soglia |
| it-friuli-venezia-giulia|68|59 | 2026-06-06 | 211 | 0.4 | 0.01 | 0.47 | 0.00 | meteo sotto la soglia |
| it-friuli-venezia-giulia|69|57 | 2026-06-06 | 211 | 0.4 | 0.01 | 0.46 | 0.00 | meteo sotto la soglia |
| it-friuli-venezia-giulia|69|58 | 2026-06-06 | 121 | 0.4 | 0.01 | 0.32 | 0.00 | meteo sotto la soglia |
| it-friuli-venezia-giulia|69|59 | 2026-06-06 | 211 | 0.4 | 0.01 | 0.47 | 0.00 | meteo sotto la soglia |
| it-friuli-venezia-giulia|84|55 | 2026-08-13 | 211 | 14.5 | 0.29 | 0.47 | 0.14 | terreno sotto la soglia |
| it-friuli-venezia-giulia|84|56 | 2026-08-13 | 331 | 14.5 | 0.29 | 0.34 | 0.10 | terreno sotto la soglia |
| it-friuli-venezia-giulia|84|57 | 2026-08-13 | 121 | 14.5 | 0.29 | 0.32 | 0.09 | terreno sotto la soglia |
| it-friuli-venezia-giulia|84|58 | 2026-08-13 | 242 | 14.5 | 0.29 | 0.47 | 0.14 | terreno sotto la soglia |
| it-friuli-venezia-giulia|85|55 | 2026-08-13 | 211 | 19.7 | 0.39 | 0.47 | 0.19 | terreno sotto la soglia |
| it-friuli-venezia-giulia|85|58 | 2026-08-13 | 242 | 19.7 | 0.39 | 0.52 | 0.20 | terreno sotto la soglia |
| it-friuli-venezia-giulia|86|54 | 2026-08-13 | 121 | 19.7 | 0.39 | 0.32 | 0.13 | terreno sotto la soglia |
| it-friuli-venezia-giulia|86|55 | 2026-08-13 | 331 | 19.7 | 0.39 | 0.40 | 0.16 | terreno sotto la soglia |
| it-friuli-venezia-giulia|87|54 | 2026-08-13 | 242 | 19.7 | 0.39 | 0.49 | 0.19 | terreno sotto la soglia |
| it-friuli-venezia-giulia|91|72 | 2026-08-13 | 313 | 0.9 | 0.02 | 0.88 | 0.02 | meteo sotto la soglia |
| it-friuli-venezia-giulia|91|73 | 2026-08-13 | 311 | 0.9 | 0.02 | 0.79 | 0.01 | meteo sotto la soglia |
| it-friuli-venezia-giulia|92|72 | 2026-08-13 | 313 | 0.9 | 0.02 | 0.88 | 0.02 | meteo sotto la soglia |
| it-friuli-venezia-giulia|92|73 | 2026-08-13 | 313 | 0.9 | 0.02 | 0.88 | 0.02 | meteo sotto la soglia |
| it-friuli-venezia-giulia|93|72 | 2026-08-13 | 333 | 0.9 | 0.02 | 0.84 | 0.02 | meteo sotto la soglia |
| it-friuli-venezia-giulia|93|73 | 2026-08-13 | 313 | 0.9 | 0.02 | 0.88 | 0.02 | meteo sotto la soglia |
| it-friuli-venezia-giulia|88|49 | 2026-08-16 | 331 | 17.6 | 0.35 | 0.38 | 0.13 | terreno sotto la soglia |

## Provenienza

| | |
|---|---|
| generato | 2026-11-26T13:36:30+00:00 |
| commit | `626506428402e7df05320c5296a6e9009362d538` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1.1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_AOI` | `it-friuli-venezia-giulia` |
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
