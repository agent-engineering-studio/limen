# Limen backtest incendio — AOI `it-veneto`

Finestra: **2026-01-01 → 2026-11-25**
Generato: 2026-11-26T13:34:44.591255+00:00
Pioggia della catena: **modello**
Soglia di allerta: **Moderate**, orizzonte di preavviso **72 h**

- Celle bruciate (perimetri EFFIS nella finestra): **59**
- Celle con almeno un'allerta: **8**
- Hit: **8**, mancati: **51** (celle bruciate); falsi allarmi: **367648** giornate-cella

## Metriche §2.5

- **Hit rate**: 13.56%
- **Tasso di base**: 3.61% (quota di giornate in allerta a prescindere dagli incendi)
- **Discriminazione**: 3.76 volte il tasso di base
- **Carico meteo**: 8.86% delle giornate-nodo della stagione con FWI in fascia alta o oltre
- **Carico per cella**: 5.89% delle giornate-cella della stagione in allerta, su tutte le celle dell'AOI
- **Discriminazione spaziale**: 2.30 volte il carico per cella
- **Giorno peggiore**: 75.38% delle celle dell'AOI in allerta insieme (2026-08-15)
- **FAR per giornata-cella**: 100.00% delle giornate-cella in allerta su celle che non hanno bruciato nelle 72 h seguenti
- **Preavviso medio**: 27.0 h

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

- Per causa: meteo sotto la soglia 22, terreno sotto la soglia 27, cancello degli avvisi 2.
- Per terra (CORINE): artificiale 20, agricola 19, bosco e seminaturale 10, acque 1, zone umide 1.
- Per mese: 06: 12, 07: 8, 08: 12, 09: 16, 10: 3.

| Cella | Incendio | CORINE | FWI max | FWI norm. max | Terreno | Punteggio max | Causa |
|---|---|---|---:|---:|---:|---:|---|
| it-veneto|78|67 | 2026-06-05 | 211 | 1.9 | 0.04 | 0.47 | 0.02 | meteo sotto la soglia |
| it-veneto|78|68 | 2026-06-05 | 211 | 1.9 | 0.04 | 0.49 | 0.02 | meteo sotto la soglia |
| it-veneto|79|67 | 2026-06-05 | 112 | 1.9 | 0.04 | 0.29 | 0.01 | meteo sotto la soglia |
| it-veneto|79|68 | 2026-06-05 | 121 | 1.9 | 0.04 | 0.32 | 0.01 | meteo sotto la soglia |
| it-veneto|63|103 | 2026-06-07 | 242 | 1.7 | 0.03 | 0.46 | 0.02 | meteo sotto la soglia |
| it-veneto|63|104 | 2026-06-07 | 242 | 1.7 | 0.03 | 0.46 | 0.02 | meteo sotto la soglia |
| it-veneto|64|103 | 2026-06-07 | 121 | 0.8 | 0.02 | 0.31 | 0.01 | meteo sotto la soglia |
| it-veneto|64|104 | 2026-06-07 | 121 | 0.8 | 0.02 | 0.31 | 0.01 | meteo sotto la soglia |
| it-veneto|65|103 | 2026-06-07 | 121 | 0.8 | 0.02 | 0.31 | 0.01 | meteo sotto la soglia |
| it-veneto|65|104 | 2026-06-07 | 121 | 0.8 | 0.02 | 0.31 | 0.01 | meteo sotto la soglia |
| it-veneto|78|69 | 2026-06-13 | 211 | 7.1 | 0.14 | 0.48 | 0.07 | meteo sotto la soglia |
| it-veneto|79|69 | 2026-06-13 | 121 | 7.1 | 0.14 | 0.32 | 0.05 | meteo sotto la soglia |
| it-veneto|24|74 | 2026-07-27 | 211 | 18.8 | 0.38 | 0.46 | 0.17 | terreno sotto la soglia |
| it-veneto|24|75 | 2026-07-27 | 211 | 18.8 | 0.38 | 0.46 | 0.17 | terreno sotto la soglia |
| it-veneto|24|76 | 2026-07-27 | 211 | 18.8 | 0.38 | 0.46 | 0.17 | terreno sotto la soglia |
| it-veneto|25|74 | 2026-07-27 | 211 | 18.8 | 0.38 | 0.46 | 0.17 | terreno sotto la soglia |
| it-veneto|25|75 | 2026-07-27 | 121 | 18.8 | 0.38 | 0.31 | 0.12 | terreno sotto la soglia |
| it-veneto|25|76 | 2026-07-27 | 211 | 18.8 | 0.38 | 0.46 | 0.17 | terreno sotto la soglia |
| it-veneto|26|74 | 2026-07-27 | 211 | 18.8 | 0.38 | 0.46 | 0.17 | terreno sotto la soglia |
| it-veneto|26|75 | 2026-07-27 | 211 | 18.8 | 0.38 | 0.46 | 0.17 | terreno sotto la soglia |
| it-veneto|65|102 | 2026-08-09 | 121 | 30.4 | 0.61 | 0.31 | 0.19 | terreno sotto la soglia |
| it-veneto|66|102 | 2026-08-09 | 121 | 30.4 | 0.61 | 0.31 | 0.19 | terreno sotto la soglia |
| it-veneto|66|103 | 2026-08-09 | 112 | 30.4 | 0.61 | 0.28 | 0.17 | terreno sotto la soglia |
| it-veneto|27|91 | 2026-08-12 | 112 | 43.8 | 0.88 | 0.28 | 0.25 | cancello degli avvisi |
| it-veneto|28|92 | 2026-08-12 | 112 | 43.8 | 0.88 | 0.28 | 0.25 | cancello degli avvisi |
| it-veneto|198|130 | 2026-08-15 | 322 | 5.3 | 0.11 | 0.91 | 0.10 | meteo sotto la soglia |
| it-veneto|198|131 | 2026-08-15 | 312 | 5.3 | 0.11 | 0.99 | 0.11 | meteo sotto la soglia |
| it-veneto|199|130 | 2026-08-15 | 312 | 5.3 | 0.11 | 0.99 | 0.10 | meteo sotto la soglia |
| it-veneto|199|131 | 2026-08-15 | 312 | 5.3 | 0.11 | 1.00 | 0.11 | meteo sotto la soglia |
| it-veneto|199|132 | 2026-08-15 | 312 | 5.3 | 0.11 | 1.00 | 0.11 | meteo sotto la soglia |
| it-veneto|200|131 | 2026-08-15 | 322 | 5.3 | 0.11 | 0.91 | 0.10 | meteo sotto la soglia |
| it-veneto|200|132 | 2026-08-15 | 321 | 5.3 | 0.11 | 0.87 | 0.09 | meteo sotto la soglia |
| it-veneto|61|18 | 2026-09-05 | 121 | 33.2 | 0.66 | 0.31 | 0.21 | terreno sotto la soglia |
| it-veneto|61|19 | 2026-09-05 | 121 | 33.2 | 0.66 | 0.31 | 0.21 | terreno sotto la soglia |
| it-veneto|62|18 | 2026-09-05 | 242 | 21.4 | 0.43 | 0.46 | 0.20 | terreno sotto la soglia |
| it-veneto|62|19 | 2026-09-05 | 242 | 21.4 | 0.43 | 0.46 | 0.20 | terreno sotto la soglia |
| it-veneto|22|126 | 2026-09-11 | 112 | 27.0 | 0.54 | 0.29 | 0.16 | terreno sotto la soglia |
| it-veneto|23|125 | 2026-09-11 | 112 | 27.0 | 0.54 | 0.29 | 0.15 | terreno sotto la soglia |
| it-veneto|23|126 | 2026-09-11 | 112 | 27.0 | 0.54 | 0.29 | 0.16 | terreno sotto la soglia |
| it-veneto|23|127 | 2026-09-11 | 511 | 27.0 | 0.54 | 0.26 | 0.14 | terreno sotto la soglia |
| it-veneto|24|126 | 2026-09-11 | 411 | 27.0 | 0.54 | 0.38 | 0.21 | terreno sotto la soglia |
| it-veneto|24|127 | 2026-09-11 | 121 | 27.0 | 0.54 | 0.32 | 0.17 | terreno sotto la soglia |
| it-veneto|29|67 | 2026-09-18 | 211 | 15.1 | 0.30 | 0.46 | 0.14 | terreno sotto la soglia |
| it-veneto|29|68 | 2026-09-18 | 211 | 15.1 | 0.30 | 0.46 | 0.14 | terreno sotto la soglia |
| it-veneto|30|67 | 2026-09-18 | 211 | 15.1 | 0.30 | 0.46 | 0.14 | terreno sotto la soglia |
| it-veneto|30|68 | 2026-09-18 | 211 | 15.1 | 0.30 | 0.46 | 0.14 | terreno sotto la soglia |
| it-veneto|31|67 | 2026-09-18 | 211 | 15.1 | 0.30 | 0.46 | 0.14 | terreno sotto la soglia |
| it-veneto|31|68 | 2026-09-18 | 112 | 15.1 | 0.30 | 0.28 | 0.09 | terreno sotto la soglia |
| it-veneto|198|132 | 2026-10-15 | 312 | 4.2 | 0.08 | 0.93 | 0.08 | meteo sotto la soglia |
| it-veneto|198|133 | 2026-10-15 | 312 | 10.0 | 0.20 | 0.93 | 0.19 | meteo sotto la soglia |
| it-veneto|199|133 | 2026-10-15 | 312 | 10.0 | 0.20 | 1.00 | 0.20 | meteo sotto la soglia |

## Provenienza

| | |
|---|---|
| generato | 2026-11-26T13:34:44+00:00 |
| commit | `626506428402e7df05320c5296a6e9009362d538` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1.1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_AOI` | `it-veneto` |
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
