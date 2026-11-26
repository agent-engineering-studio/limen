# Limen backtest incendio — AOI `it-liguria`

Finestra: **2024-01-01 → 2024-12-31**
Generato: 2026-11-26T14:53:30.640762+00:00
Pioggia della catena: **modello**
Soglia di allerta: **Moderate**, orizzonte di preavviso **72 h**

- Celle bruciate (perimetri EFFIS nella finestra): **19**
- Celle con almeno un'allerta: **6**
- Hit: **6**, mancati: **13** (celle bruciate); falsi allarmi: **143851** giornate-cella

## Metriche §2.5

- **Hit rate**: 31.58%
- **Tasso di base**: 10.68% (quota di giornate in allerta a prescindere dagli incendi)
- **Discriminazione**: 2.96 volte il tasso di base
- **Carico meteo**: 1.72% delle giornate-nodo della stagione con FWI in fascia alta o oltre
- **Carico per cella**: 7.94% delle giornate-cella della stagione in allerta, su tutte le celle dell'AOI
- **Discriminazione spaziale**: 3.98 volte il carico per cella
- **Giorno peggiore**: 89.16% delle celle dell'AOI in allerta insieme (2024-08-13)
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

- Per causa: meteo sotto la soglia 10, terreno sotto la soglia 3.
- Per terra (CORINE): bosco e seminaturale 12, agricola 1.
- Per mese: 12: 13.

| Cella | Incendio | CORINE | FWI max | FWI norm. max | Terreno | Punteggio max | Causa |
|---|---|---|---:|---:|---:|---:|---|
| it-liguria|67|84 | 2024-12-24 | 311 | 6.4 | 0.18 | 0.74 | 0.14 | meteo sotto la soglia |
| it-liguria|67|85 | 2024-12-24 | 242 | 6.4 | 0.18 | 0.56 | 0.10 | meteo sotto la soglia |
| it-liguria|67|86 | 2024-12-24 | 324 | 6.4 | 0.18 | 0.86 | 0.16 | meteo sotto la soglia |
| it-liguria|68|84 | 2024-12-24 | 311 | 6.4 | 0.18 | 0.75 | 0.14 | meteo sotto la soglia |
| it-liguria|68|85 | 2024-12-24 | 311 | 6.4 | 0.18 | 0.75 | 0.14 | meteo sotto la soglia |
| it-liguria|68|86 | 2024-12-24 | 311 | 6.4 | 0.18 | 0.74 | 0.13 | meteo sotto la soglia |
| it-liguria|68|87 | 2024-12-24 | 311 | 6.4 | 0.18 | 0.76 | 0.14 | meteo sotto la soglia |
| it-liguria|69|85 | 2024-12-24 | 311 | 6.4 | 0.18 | 0.74 | 0.14 | meteo sotto la soglia |
| it-liguria|69|86 | 2024-12-24 | 324 | 6.4 | 0.18 | 0.84 | 0.15 | meteo sotto la soglia |
| it-liguria|69|87 | 2024-12-24 | 311 | 6.4 | 0.18 | 0.73 | 0.13 | meteo sotto la soglia |
| it-liguria|10|30 | 2024-12-26 | 324 | 9.2 | 0.26 | 0.87 | 0.23 | terreno sotto la soglia |
| it-liguria|11|30 | 2024-12-26 | 321 | 9.2 | 0.26 | 0.84 | 0.22 | terreno sotto la soglia |
| it-liguria|12|30 | 2024-12-26 | 311 | 9.2 | 0.26 | 0.77 | 0.20 | terreno sotto la soglia |

## Provenienza

| | |
|---|---|
| generato | 2026-11-26T14:53:30+00:00 |
| commit | `89882ad5b11450cec70d66f6832298a095e64b98` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1.1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_AOI` | `it-liguria` |
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
