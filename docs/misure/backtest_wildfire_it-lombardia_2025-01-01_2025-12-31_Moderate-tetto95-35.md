# Limen backtest incendio — AOI `it-lombardia`

Finestra: **2025-01-01 → 2025-12-31**
Generato: 2026-11-26T14:55:40.226942+00:00
Pioggia della catena: **modello**
Soglia di allerta: **Moderate**, orizzonte di preavviso **72 h**

- Celle bruciate (perimetri EFFIS nella finestra): **11**
- Celle con almeno un'allerta: **0**
- Hit: **0**, mancati: **11** (celle bruciate); falsi allarmi: **272122** giornate-cella

## Metriche §2.5

- **Hit rate**: 0.00%
- **Tasso di base**: 1.47% (quota di giornate in allerta a prescindere dagli incendi)
- **Discriminazione**: 0.00 volte il tasso di base
- **Carico meteo**: 2.07% delle giornate-nodo della stagione con FWI in fascia alta o oltre
- **Carico per cella**: 3.02% delle giornate-cella della stagione in allerta, su tutte le celle dell'AOI
- **Discriminazione spaziale**: 0.00 volte il carico per cella
- **Giorno peggiore**: 63.57% delle celle dell'AOI in allerta insieme (2025-06-29)
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

- Per causa: meteo sotto la soglia 11.
- Per terra (CORINE): agricola 5, bosco e seminaturale 5, artificiale 1.
- Per mese: 01: 4, 04: 7.

| Cella | Incendio | CORINE | FWI max | FWI norm. max | Terreno | Punteggio max | Causa |
|---|---|---|---:|---:|---:|---:|---|
| it-lombardia|50|112 | 2025-01-30 | 211 | 0.0 | 0.00 | 0.47 | 0.00 | meteo sotto la soglia |
| it-lombardia|50|113 | 2025-01-30 | 211 | 0.0 | 0.00 | 0.47 | 0.00 | meteo sotto la soglia |
| it-lombardia|51|112 | 2025-01-30 | 211 | 0.0 | 0.00 | 0.47 | 0.00 | meteo sotto la soglia |
| it-lombardia|51|113 | 2025-01-30 | 121 | 0.0 | 0.00 | 0.32 | 0.00 | meteo sotto la soglia |
| it-lombardia|126|141 | 2025-04-11 | 231 | 8.4 | 0.24 | 0.75 | 0.18 | meteo sotto la soglia |
| it-lombardia|126|142 | 2025-04-11 | 313 | 8.4 | 0.24 | 0.85 | 0.20 | meteo sotto la soglia |
| it-lombardia|127|141 | 2025-04-11 | 321 | 8.4 | 0.24 | 0.84 | 0.20 | meteo sotto la soglia |
| it-lombardia|127|142 | 2025-04-11 | 321 | 8.4 | 0.24 | 0.85 | 0.20 | meteo sotto la soglia |
| it-lombardia|127|143 | 2025-04-11 | 231 | 8.4 | 0.24 | 0.75 | 0.18 | meteo sotto la soglia |
| it-lombardia|128|141 | 2025-04-11 | 321 | 8.4 | 0.24 | 0.85 | 0.20 | meteo sotto la soglia |
| it-lombardia|128|142 | 2025-04-11 | 321 | 8.4 | 0.24 | 0.83 | 0.20 | meteo sotto la soglia |

## Provenienza

| | |
|---|---|
| generato | 2026-11-26T14:55:40+00:00 |
| commit | `89882ad5b11450cec70d66f6832298a095e64b98` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1.1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_AOI` | `it-lombardia` |
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
