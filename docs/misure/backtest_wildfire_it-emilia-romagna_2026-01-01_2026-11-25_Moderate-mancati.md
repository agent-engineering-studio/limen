# Limen backtest incendio — AOI `it-emilia-romagna`

Finestra: **2026-01-01 → 2026-11-25**
Generato: 2026-11-26T13:35:42.754942+00:00
Pioggia della catena: **modello**
Soglia di allerta: **Moderate**, orizzonte di preavviso **72 h**

- Celle bruciate (perimetri EFFIS nella finestra): **100**
- Celle con almeno un'allerta: **38**
- Hit: **38**, mancati: **62** (celle bruciate); falsi allarmi: **1108691** giornate-cella

## Metriche §2.5

- **Hit rate**: 38.00%
- **Tasso di base**: 14.36% (quota di giornate in allerta a prescindere dagli incendi)
- **Discriminazione**: 2.65 volte il tasso di base
- **Carico meteo**: 14.55% delle giornate-nodo della stagione con FWI in fascia alta o oltre
- **Carico per cella**: 14.52% delle giornate-cella della stagione in allerta, su tutte le celle dell'AOI
- **Discriminazione spaziale**: 2.62 volte il carico per cella
- **Giorno peggiore**: 92.49% delle celle dell'AOI in allerta insieme (2026-08-14)
- **FAR per giornata-cella**: 99.99% delle giornate-cella in allerta su celle che non hanno bruciato nelle 72 h seguenti
- **Preavviso medio**: 65.7 h

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

- Per causa: meteo sotto la soglia 14, terreno sotto la soglia 48.
- Per terra (CORINE): agricola 45, artificiale 9, bosco e seminaturale 8.
- Per mese: 04: 8, 08: 18, 09: 23, 10: 13.

| Cella | Incendio | CORINE | FWI max | FWI norm. max | Terreno | Punteggio max | Causa |
|---|---|---|---:|---:|---:|---:|---|
| it-emilia-romagna|74|29 | 2026-04-01 | 333 | 4.6 | 0.09 | 0.79 | 0.07 | meteo sotto la soglia |
| it-emilia-romagna|74|30 | 2026-04-01 | 324 | 4.6 | 0.09 | 0.89 | 0.08 | meteo sotto la soglia |
| it-emilia-romagna|75|29 | 2026-04-01 | 311 | 4.6 | 0.09 | 0.76 | 0.07 | meteo sotto la soglia |
| it-emilia-romagna|36|138 | 2026-04-06 | 311 | 7.1 | 0.14 | 0.78 | 0.11 | meteo sotto la soglia |
| it-emilia-romagna|36|139 | 2026-04-06 | 311 | 7.1 | 0.14 | 0.77 | 0.11 | meteo sotto la soglia |
| it-emilia-romagna|37|138 | 2026-04-06 | 311 | 7.1 | 0.14 | 0.79 | 0.11 | meteo sotto la soglia |
| it-emilia-romagna|37|139 | 2026-04-06 | 311 | 7.1 | 0.14 | 0.79 | 0.11 | meteo sotto la soglia |
| it-emilia-romagna|37|140 | 2026-04-06 | 311 | 7.1 | 0.14 | 0.78 | 0.11 | meteo sotto la soglia |
| it-emilia-romagna|81|163 | 2026-08-01 | 122 | 27.3 | 0.55 | 0.32 | 0.18 | terreno sotto la soglia |
| it-emilia-romagna|81|164 | 2026-08-01 | 121 | 27.3 | 0.55 | 0.32 | 0.17 | terreno sotto la soglia |
| it-emilia-romagna|82|162 | 2026-08-01 | 121 | 27.3 | 0.55 | 0.32 | 0.17 | terreno sotto la soglia |
| it-emilia-romagna|82|163 | 2026-08-01 | 121 | 27.3 | 0.55 | 0.31 | 0.17 | terreno sotto la soglia |
| it-emilia-romagna|83|162 | 2026-08-01 | 121 | 27.3 | 0.55 | 0.32 | 0.17 | terreno sotto la soglia |
| it-emilia-romagna|76|241 | 2026-08-19 | 121 | 22.2 | 0.44 | 0.32 | 0.14 | terreno sotto la soglia |
| it-emilia-romagna|76|242 | 2026-08-19 | 211 | 22.2 | 0.44 | 0.47 | 0.21 | terreno sotto la soglia |
| it-emilia-romagna|77|241 | 2026-08-19 | 121 | 22.2 | 0.44 | 0.32 | 0.14 | terreno sotto la soglia |
| it-emilia-romagna|77|242 | 2026-08-19 | 121 | 22.2 | 0.44 | 0.33 | 0.14 | terreno sotto la soglia |
| it-emilia-romagna|78|241 | 2026-08-19 | 211 | 22.2 | 0.44 | 0.47 | 0.21 | terreno sotto la soglia |
| it-emilia-romagna|78|242 | 2026-08-19 | 121 | 22.2 | 0.44 | 0.32 | 0.14 | terreno sotto la soglia |
| it-emilia-romagna|75|207 | 2026-08-30 | 211 | 24.5 | 0.49 | 0.46 | 0.23 | terreno sotto la soglia |
| it-emilia-romagna|76|206 | 2026-08-30 | 211 | 24.5 | 0.49 | 0.46 | 0.23 | terreno sotto la soglia |
| it-emilia-romagna|76|207 | 2026-08-30 | 211 | 24.5 | 0.49 | 0.46 | 0.23 | terreno sotto la soglia |
| it-emilia-romagna|76|208 | 2026-08-30 | 211 | 24.5 | 0.49 | 0.46 | 0.23 | terreno sotto la soglia |
| it-emilia-romagna|77|206 | 2026-08-30 | 211 | 24.5 | 0.49 | 0.46 | 0.23 | terreno sotto la soglia |
| it-emilia-romagna|77|207 | 2026-08-30 | 211 | 24.5 | 0.49 | 0.46 | 0.23 | terreno sotto la soglia |
| it-emilia-romagna|77|208 | 2026-08-30 | 242 | 24.5 | 0.49 | 0.46 | 0.23 | terreno sotto la soglia |
| it-emilia-romagna|91|153 | 2026-09-16 | 242 | 19.8 | 0.40 | 0.46 | 0.18 | terreno sotto la soglia |
| it-emilia-romagna|91|154 | 2026-09-16 | 242 | 19.8 | 0.40 | 0.46 | 0.18 | terreno sotto la soglia |
| it-emilia-romagna|92|153 | 2026-09-16 | 242 | 19.8 | 0.40 | 0.46 | 0.18 | terreno sotto la soglia |
| it-emilia-romagna|92|154 | 2026-09-16 | 211 | 19.8 | 0.40 | 0.46 | 0.18 | terreno sotto la soglia |
| it-emilia-romagna|127|231 | 2026-09-29 | 213 | 15.6 | 0.31 | 0.47 | 0.15 | terreno sotto la soglia |
| it-emilia-romagna|127|232 | 2026-09-29 | 213 | 13.7 | 0.27 | 0.47 | 0.13 | terreno sotto la soglia |
| it-emilia-romagna|128|230 | 2026-09-29 | 213 | 15.6 | 0.31 | 0.47 | 0.15 | terreno sotto la soglia |
| it-emilia-romagna|128|231 | 2026-09-29 | 211 | 15.6 | 0.31 | 0.47 | 0.15 | terreno sotto la soglia |
| it-emilia-romagna|128|232 | 2026-09-29 | 213 | 13.7 | 0.27 | 0.47 | 0.13 | terreno sotto la soglia |
| it-emilia-romagna|129|230 | 2026-09-29 | 213 | 15.6 | 0.31 | 0.47 | 0.15 | terreno sotto la soglia |
| it-emilia-romagna|129|231 | 2026-09-29 | 213 | 15.6 | 0.31 | 0.47 | 0.15 | terreno sotto la soglia |
| it-emilia-romagna|129|232 | 2026-09-29 | 213 | 13.7 | 0.27 | 0.47 | 0.13 | terreno sotto la soglia |
| it-emilia-romagna|130|230 | 2026-09-29 | 213 | 15.6 | 0.31 | 0.47 | 0.15 | terreno sotto la soglia |
| it-emilia-romagna|130|231 | 2026-09-29 | 213 | 15.6 | 0.31 | 0.47 | 0.15 | terreno sotto la soglia |
| it-emilia-romagna|130|232 | 2026-09-29 | 213 | 13.7 | 0.27 | 0.47 | 0.13 | terreno sotto la soglia |
| it-emilia-romagna|123|229 | 2026-09-30 | 211 | 20.7 | 0.41 | 0.47 | 0.19 | terreno sotto la soglia |
| it-emilia-romagna|124|228 | 2026-09-30 | 211 | 20.7 | 0.41 | 0.47 | 0.19 | terreno sotto la soglia |
| it-emilia-romagna|124|229 | 2026-09-30 | 211 | 20.7 | 0.41 | 0.47 | 0.19 | terreno sotto la soglia |
| it-emilia-romagna|124|230 | 2026-09-30 | 211 | 20.7 | 0.41 | 0.47 | 0.19 | terreno sotto la soglia |
| it-emilia-romagna|125|228 | 2026-09-30 | 211 | 20.7 | 0.41 | 0.47 | 0.19 | terreno sotto la soglia |
| it-emilia-romagna|125|229 | 2026-09-30 | 213 | 20.7 | 0.41 | 0.47 | 0.19 | terreno sotto la soglia |
| it-emilia-romagna|125|230 | 2026-09-30 | 213 | 20.7 | 0.41 | 0.47 | 0.19 | terreno sotto la soglia |
| it-emilia-romagna|126|229 | 2026-09-30 | 211 | 15.6 | 0.31 | 0.46 | 0.15 | terreno sotto la soglia |
| it-emilia-romagna|123|223 | 2026-10-03 | 213 | 21.4 | 0.43 | 0.47 | 0.20 | terreno sotto la soglia |
| it-emilia-romagna|123|224 | 2026-10-03 | 213 | 21.4 | 0.43 | 0.47 | 0.20 | terreno sotto la soglia |
| it-emilia-romagna|124|223 | 2026-10-03 | 213 | 21.4 | 0.43 | 0.47 | 0.20 | terreno sotto la soglia |
| it-emilia-romagna|124|224 | 2026-10-03 | 213 | 21.4 | 0.43 | 0.47 | 0.20 | terreno sotto la soglia |
| it-emilia-romagna|124|225 | 2026-10-03 | 213 | 21.4 | 0.43 | 0.47 | 0.20 | terreno sotto la soglia |
| it-emilia-romagna|126|230 | 2026-10-04 | 213 | 21.5 | 0.43 | 0.47 | 0.20 | terreno sotto la soglia |
| it-emilia-romagna|127|230 | 2026-10-04 | 213 | 23.3 | 0.47 | 0.46 | 0.22 | terreno sotto la soglia |
| it-emilia-romagna|128|228 | 2026-10-20 | 213 | 10.3 | 0.21 | 0.47 | 0.10 | meteo sotto la soglia |
| it-emilia-romagna|128|229 | 2026-10-20 | 213 | 10.3 | 0.21 | 0.47 | 0.10 | meteo sotto la soglia |
| it-emilia-romagna|129|228 | 2026-10-20 | 213 | 10.3 | 0.21 | 0.46 | 0.10 | meteo sotto la soglia |
| it-emilia-romagna|129|229 | 2026-10-20 | 213 | 10.3 | 0.21 | 0.47 | 0.10 | meteo sotto la soglia |
| it-emilia-romagna|130|228 | 2026-10-20 | 213 | 10.3 | 0.21 | 0.47 | 0.10 | meteo sotto la soglia |
| it-emilia-romagna|130|229 | 2026-10-20 | 211 | 10.3 | 0.21 | 0.47 | 0.10 | meteo sotto la soglia |

## Provenienza

| | |
|---|---|
| generato | 2026-11-26T13:35:42+00:00 |
| commit | `626506428402e7df05320c5296a6e9009362d538` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1.1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_AOI` | `it-emilia-romagna` |
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
