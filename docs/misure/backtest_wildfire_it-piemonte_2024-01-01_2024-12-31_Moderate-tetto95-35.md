# Limen backtest incendio — AOI `it-piemonte`

Finestra: **2024-01-01 → 2024-12-31**
Generato: 2026-11-26T14:52:48.707008+00:00
Pioggia della catena: **modello**
Soglia di allerta: **Moderate**, orizzonte di preavviso **72 h**

- Celle bruciate (perimetri EFFIS nella finestra): **10**
- Celle con almeno un'allerta: **0**
- Hit: **0**, mancati: **10** (celle bruciate); falsi allarmi: **222304** giornate-cella

## Metriche §2.5

- **Hit rate**: 0.00%
- **Tasso di base**: 3.41% (quota di giornate in allerta a prescindere dagli incendi)
- **Discriminazione**: 0.00 volte il tasso di base
- **Carico meteo**: 1.35% delle giornate-nodo della stagione con FWI in fascia alta o oltre
- **Carico per cella**: 2.76% delle giornate-cella della stagione in allerta, su tutte le celle dell'AOI
- **Discriminazione spaziale**: 0.00 volte il carico per cella
- **Giorno peggiore**: 45.93% delle celle dell'AOI in allerta insieme (2024-08-31)
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

- Per causa: nessun dato meteo 10.
- Per terra (CORINE): bosco e seminaturale 8, agricola 2.
- Per mese: 01: 4, 02: 6.

| Cella | Incendio | CORINE | FWI max | FWI norm. max | Terreno | Punteggio max | Causa |
|---|---|---|---:|---:|---:|---:|---|
| it-piemonte|122|54 | 2024-01-24 | 311 | — | — | — | — | nessun dato meteo |
| it-piemonte|122|55 | 2024-01-24 | 311 | — | — | — | — | nessun dato meteo |
| it-piemonte|123|54 | 2024-01-24 | 311 | — | — | — | — | nessun dato meteo |
| it-piemonte|123|55 | 2024-01-24 | 311 | — | — | — | — | nessun dato meteo |
| it-piemonte|164|101 | 2024-02-20 | 321 | — | — | — | — | nessun dato meteo |
| it-piemonte|164|102 | 2024-02-20 | 243 | — | — | — | — | nessun dato meteo |
| it-piemonte|164|103 | 2024-02-20 | 243 | — | — | — | — | nessun dato meteo |
| it-piemonte|165|101 | 2024-02-20 | 311 | — | — | — | — | nessun dato meteo |
| it-piemonte|165|102 | 2024-02-20 | 321 | — | — | — | — | nessun dato meteo |
| it-piemonte|165|103 | 2024-02-20 | 321 | — | — | — | — | nessun dato meteo |

## Provenienza

| | |
|---|---|
| generato | 2026-11-26T14:52:48+00:00 |
| commit | `89882ad5b11450cec70d66f6832298a095e64b98` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1.1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_AOI` | `it-piemonte` |
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
