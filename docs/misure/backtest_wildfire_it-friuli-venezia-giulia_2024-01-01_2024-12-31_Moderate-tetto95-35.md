# Limen backtest incendio — AOI `it-friuli-venezia-giulia`

Finestra: **2024-01-01 → 2024-12-31**
Generato: 2026-11-26T14:53:56.170404+00:00
Pioggia della catena: **modello**
Soglia di allerta: **Moderate**, orizzonte di preavviso **72 h**

- Celle bruciate (perimetri EFFIS nella finestra): **13**
- Celle con almeno un'allerta: **0**
- Hit: **0**, mancati: **13** (celle bruciate); falsi allarmi: **112574** giornate-cella

## Metriche §2.5

- **Hit rate**: 0.00%
- **Tasso di base**: 2.52% (quota di giornate in allerta a prescindere dagli incendi)
- **Discriminazione**: 0.00 volte il tasso di base
- **Carico meteo**: 2.19% delle giornate-nodo della stagione con FWI in fascia alta o oltre
- **Carico per cella**: 4.41% delle giornate-cella della stagione in allerta, su tutte le celle dell'AOI
- **Discriminazione spaziale**: 0.00 volte il carico per cella
- **Giorno peggiore**: 74.60% delle celle dell'AOI in allerta insieme (2024-09-02)
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

- Per causa: meteo sotto la soglia 13.
- Per terra (CORINE): bosco e seminaturale 13.
- Per mese: 09: 13.

| Cella | Incendio | CORINE | FWI max | FWI norm. max | Terreno | Punteggio max | Causa |
|---|---|---|---:|---:|---:|---:|---|
| it-friuli-venezia-giulia|90|62 | 2024-09-01 | 333 | 5.1 | 0.15 | 0.84 | 0.12 | meteo sotto la soglia |
| it-friuli-venezia-giulia|90|63 | 2024-09-01 | 313 | 5.1 | 0.15 | 0.87 | 0.13 | meteo sotto la soglia |
| it-friuli-venezia-giulia|91|61 | 2024-09-01 | 324 | 5.1 | 0.15 | 0.91 | 0.13 | meteo sotto la soglia |
| it-friuli-venezia-giulia|91|62 | 2024-09-01 | 313 | 5.1 | 0.15 | 0.88 | 0.13 | meteo sotto la soglia |
| it-friuli-venezia-giulia|91|63 | 2024-09-01 | 313 | 5.1 | 0.15 | 0.88 | 0.13 | meteo sotto la soglia |
| it-friuli-venezia-giulia|91|64 | 2024-09-01 | 313 | 5.1 | 0.15 | 0.88 | 0.13 | meteo sotto la soglia |
| it-friuli-venezia-giulia|92|61 | 2024-09-01 | 311 | 5.1 | 0.15 | 0.79 | 0.11 | meteo sotto la soglia |
| it-friuli-venezia-giulia|92|62 | 2024-09-01 | 313 | 5.1 | 0.15 | 0.88 | 0.13 | meteo sotto la soglia |
| it-friuli-venezia-giulia|92|63 | 2024-09-01 | 313 | 5.1 | 0.15 | 0.88 | 0.13 | meteo sotto la soglia |
| it-friuli-venezia-giulia|92|64 | 2024-09-01 | 313 | 5.1 | 0.15 | 0.87 | 0.13 | meteo sotto la soglia |
| it-friuli-venezia-giulia|93|61 | 2024-09-01 | 311 | 5.1 | 0.15 | 0.79 | 0.11 | meteo sotto la soglia |
| it-friuli-venezia-giulia|93|62 | 2024-09-01 | 313 | 5.1 | 0.15 | 0.88 | 0.13 | meteo sotto la soglia |
| it-friuli-venezia-giulia|93|63 | 2024-09-01 | 311 | 5.1 | 0.15 | 0.78 | 0.11 | meteo sotto la soglia |

## Provenienza

| | |
|---|---|
| generato | 2026-11-26T14:53:56+00:00 |
| commit | `89882ad5b11450cec70d66f6832298a095e64b98` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1.1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_AOI` | `it-friuli-venezia-giulia` |
| `LIMEN_BACKTEST_WILDFIRE_END` | `2024-12-31` |
| `LIMEN_BACKTEST_WILDFIRE_LEVEL` | `Moderate` |
| `LIMEN_BACKTEST_WILDFIRE_START` | `2024-01-01` |
| `LIMEN_BACKTEST_WILDFIRE_TETTO` | `95:35:6-9` |
| `LIMEN_BACKUP_DIR` | `<percorso locale>` |
| `LIMEN_DATA_ROOT` | `<percorso locale>` |
| `LIMEN_DOMINIO` | `localhost` |
| `LIMEN_IMAGE_PREFIX` | `ghcr.io/agent-engineering-studio/limen-` |
| `LIMEN_IMAGE_TAG` | `sha-ecddbd8` |
| `LIMEN_IMPERVIOUSNESS_RASTER` | `<percorso locale>` |
| `LIMEN_PROXY_BIND` | `127.0.0.1` |
| `LIMEN_REPORTS_DIR` | `<percorso locale>` |
