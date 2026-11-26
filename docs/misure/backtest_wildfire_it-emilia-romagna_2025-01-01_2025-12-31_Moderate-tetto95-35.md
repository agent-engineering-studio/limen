# Limen backtest incendio — AOI `it-emilia-romagna`

Finestra: **2025-01-01 → 2025-12-31**
Generato: 2026-11-26T14:58:24.341447+00:00
Pioggia della catena: **modello**
Soglia di allerta: **Moderate**, orizzonte di preavviso **72 h**

- Celle bruciate (perimetri EFFIS nella finestra): **22**
- Celle con almeno un'allerta: **4**
- Hit: **4**, mancati: **18** (celle bruciate); falsi allarmi: **908193** giornate-cella

## Metriche §2.5

- **Hit rate**: 18.18%
- **Tasso di base**: 11.37% (quota di giornate in allerta a prescindere dagli incendi)
- **Discriminazione**: 1.60 volte il tasso di base
- **Carico meteo**: 5.66% delle giornate-nodo della stagione con FWI in fascia alta o oltre
- **Carico per cella**: 10.72% delle giornate-cella della stagione in allerta, su tutte le celle dell'AOI
- **Discriminazione spaziale**: 1.70 volte il carico per cella
- **Giorno peggiore**: 93.16% delle celle dell'AOI in allerta insieme (2025-06-30)
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

- Per causa: meteo sotto la soglia 18.
- Per terra (CORINE): agricola 18.
- Per mese: 02: 7, 08: 3, 10: 8.

| Cella | Incendio | CORINE | FWI max | FWI norm. max | Terreno | Punteggio max | Causa |
|---|---|---|---:|---:|---:|---:|---|
| it-emilia-romagna|71|194 | 2025-02-20 | 211 | 0.5 | 0.01 | 0.46 | 0.01 | meteo sotto la soglia |
| it-emilia-romagna|72|193 | 2025-02-20 | 211 | 0.5 | 0.01 | 0.46 | 0.01 | meteo sotto la soglia |
| it-emilia-romagna|72|194 | 2025-02-20 | 211 | 0.5 | 0.01 | 0.46 | 0.01 | meteo sotto la soglia |
| it-emilia-romagna|72|195 | 2025-02-20 | 211 | 0.5 | 0.01 | 0.46 | 0.01 | meteo sotto la soglia |
| it-emilia-romagna|73|193 | 2025-02-20 | 211 | 0.5 | 0.01 | 0.47 | 0.01 | meteo sotto la soglia |
| it-emilia-romagna|73|194 | 2025-02-20 | 211 | 0.5 | 0.01 | 0.46 | 0.01 | meteo sotto la soglia |
| it-emilia-romagna|73|195 | 2025-02-20 | 242 | 0.5 | 0.01 | 0.46 | 0.01 | meteo sotto la soglia |
| it-emilia-romagna|126|179 | 2025-08-26 | 211 | 2.5 | 0.07 | 0.47 | 0.03 | meteo sotto la soglia |
| it-emilia-romagna|126|180 | 2025-08-26 | 211 | 2.5 | 0.07 | 0.46 | 0.03 | meteo sotto la soglia |
| it-emilia-romagna|127|180 | 2025-08-26 | 211 | 2.5 | 0.07 | 0.47 | 0.03 | meteo sotto la soglia |
| it-emilia-romagna|131|226 | 2025-10-04 | 213 | 5.6 | 0.16 | 0.47 | 0.07 | meteo sotto la soglia |
| it-emilia-romagna|131|227 | 2025-10-04 | 213 | 5.6 | 0.16 | 0.47 | 0.07 | meteo sotto la soglia |
| it-emilia-romagna|132|226 | 2025-10-04 | 213 | 5.6 | 0.16 | 0.47 | 0.07 | meteo sotto la soglia |
| it-emilia-romagna|132|227 | 2025-10-04 | 213 | 5.6 | 0.16 | 0.47 | 0.07 | meteo sotto la soglia |
| it-emilia-romagna|133|226 | 2025-10-04 | 211 | 5.6 | 0.16 | 0.47 | 0.07 | meteo sotto la soglia |
| it-emilia-romagna|133|227 | 2025-10-04 | 213 | 5.6 | 0.16 | 0.47 | 0.07 | meteo sotto la soglia |
| it-emilia-romagna|134|226 | 2025-10-04 | 211 | 5.6 | 0.16 | 0.47 | 0.07 | meteo sotto la soglia |
| it-emilia-romagna|134|227 | 2025-10-04 | 213 | 5.6 | 0.16 | 0.46 | 0.07 | meteo sotto la soglia |

## Provenienza

| | |
|---|---|
| generato | 2026-11-26T14:58:24+00:00 |
| commit | `89882ad5b11450cec70d66f6832298a095e64b98` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1.1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_AOI` | `it-emilia-romagna` |
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
