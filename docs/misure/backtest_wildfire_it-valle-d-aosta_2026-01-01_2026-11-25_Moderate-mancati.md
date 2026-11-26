# Limen backtest incendio — AOI `it-valle-d-aosta`

Finestra: **2026-01-01 → 2026-11-25**
Generato: 2026-11-26T13:37:15.171699+00:00
Pioggia della catena: **modello**
Soglia di allerta: **Moderate**, orizzonte di preavviso **72 h**

- Celle bruciate (perimetri EFFIS nella finestra): **6**
- Celle con almeno un'allerta: **0**
- Hit: **0**, mancati: **6** (celle bruciate); falsi allarmi: **128025** giornate-cella

## Metriche §2.5

- **Hit rate**: 0.00%
- **Tasso di base**: 25.18% (quota di giornate in allerta a prescindere dagli incendi)
- **Discriminazione**: 0.00 volte il tasso di base
- **Carico meteo**: 5.27% delle giornate-nodo della stagione con FWI in fascia alta o oltre
- **Carico per cella**: 11.27% delle giornate-cella della stagione in allerta, su tutte le celle dell'AOI
- **Discriminazione spaziale**: 0.00 volte il carico per cella
- **Giorno peggiore**: 66.64% delle celle dell'AOI in allerta insieme (2026-07-08)
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

- Per causa: meteo sotto la soglia 6.
- Per terra (CORINE): bosco e seminaturale 4, agricola 2.
- Per mese: 04: 6.

| Cella | Incendio | CORINE | FWI max | FWI norm. max | Terreno | Punteggio max | Causa |
|---|---|---|---:|---:|---:|---:|---|
| it-valle-d-aosta|31|54 | 2026-04-02 | 324 | 4.0 | 0.08 | 0.87 | 0.07 | meteo sotto la soglia |
| it-valle-d-aosta|31|55 | 2026-04-02 | 243 | 4.0 | 0.08 | 0.57 | 0.05 | meteo sotto la soglia |
| it-valle-d-aosta|32|54 | 2026-04-02 | 324 | 4.0 | 0.08 | 0.88 | 0.07 | meteo sotto la soglia |
| it-valle-d-aosta|32|55 | 2026-04-02 | 243 | 4.0 | 0.08 | 0.56 | 0.05 | meteo sotto la soglia |
| it-valle-d-aosta|33|54 | 2026-04-02 | 312 | 4.0 | 0.08 | 0.95 | 0.08 | meteo sotto la soglia |
| it-valle-d-aosta|33|55 | 2026-04-02 | 324 | 4.0 | 0.08 | 0.86 | 0.07 | meteo sotto la soglia |

## Provenienza

| | |
|---|---|
| generato | 2026-11-26T13:37:15+00:00 |
| commit | `626506428402e7df05320c5296a6e9009362d538` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1.1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_AOI` | `it-valle-d-aosta` |
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
