# Limen backtest incendio — AOI `it-piemonte`

Finestra: **2025-01-01 → 2025-12-31**
Generato: 2026-11-26T14:57:04.962802+00:00
Pioggia della catena: **modello**
Soglia di allerta: **Moderate**, orizzonte di preavviso **72 h**

- Celle bruciate (perimetri EFFIS nella finestra): **12**
- Celle con almeno un'allerta: **4**
- Hit: **4**, mancati: **8** (celle bruciate); falsi allarmi: **451766** giornate-cella

## Metriche §2.5

- **Hit rate**: 33.33%
- **Tasso di base**: 3.40% (quota di giornate in allerta a prescindere dagli incendi)
- **Discriminazione**: 9.80 volte il tasso di base
- **Carico meteo**: 2.34% delle giornate-nodo della stagione con FWI in fascia alta o oltre
- **Carico per cella**: 4.74% delle giornate-cella della stagione in allerta, su tutte le celle dell'AOI
- **Discriminazione spaziale**: 7.04 volte il carico per cella
- **Giorno peggiore**: 59.87% delle celle dell'AOI in allerta insieme (2025-06-29)
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

- Per causa: meteo sotto la soglia 8.
- Per terra (CORINE): bosco e seminaturale 8.
- Per mese: 11: 8.

| Cella | Incendio | CORINE | FWI max | FWI norm. max | Terreno | Punteggio max | Causa |
|---|---|---|---:|---:|---:|---:|---|
| it-piemonte|25|87 | 2025-11-11 | 311 | 0.4 | 0.01 | 0.75 | 0.01 | meteo sotto la soglia |
| it-piemonte|25|88 | 2025-11-11 | 311 | 0.4 | 0.01 | 0.75 | 0.01 | meteo sotto la soglia |
| it-piemonte|25|89 | 2025-11-11 | 311 | 0.4 | 0.01 | 0.75 | 0.01 | meteo sotto la soglia |
| it-piemonte|26|87 | 2025-11-11 | 311 | 0.4 | 0.01 | 0.76 | 0.01 | meteo sotto la soglia |
| it-piemonte|26|88 | 2025-11-11 | 311 | 0.4 | 0.01 | 0.76 | 0.01 | meteo sotto la soglia |
| it-piemonte|26|89 | 2025-11-11 | 311 | 0.4 | 0.01 | 0.73 | 0.01 | meteo sotto la soglia |
| it-piemonte|27|87 | 2025-11-11 | 311 | 0.4 | 0.01 | 0.75 | 0.01 | meteo sotto la soglia |
| it-piemonte|27|88 | 2025-11-11 | 311 | 0.4 | 0.01 | 0.75 | 0.01 | meteo sotto la soglia |

## Provenienza

| | |
|---|---|
| generato | 2026-11-26T14:57:04+00:00 |
| commit | `89882ad5b11450cec70d66f6832298a095e64b98` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1.1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_AOI` | `it-piemonte` |
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
