# Limen backtest incendio — AOI `it-lombardia`

Finestra: **2026-01-01 → 2026-11-25**
Generato: 2026-11-26T13:32:56.246344+00:00
Pioggia della catena: **modello**
Soglia di allerta: **Moderate**, orizzonte di preavviso **72 h**

- Celle bruciate (perimetri EFFIS nella finestra): **109**
- Celle con almeno un'allerta: **22**
- Hit: **22**, mancati: **87** (celle bruciate); falsi allarmi: **530764** giornate-cella

## Metriche §2.5

- **Hit rate**: 20.18%
- **Tasso di base**: 5.95% (quota di giornate in allerta a prescindere dagli incendi)
- **Discriminazione**: 3.39 volte il tasso di base
- **Carico meteo**: 9.94% delle giornate-nodo della stagione con FWI in fascia alta o oltre
- **Carico per cella**: 6.53% delle giornate-cella della stagione in allerta, su tutte le celle dell'AOI
- **Discriminazione spaziale**: 3.09 volte il carico per cella
- **Giorno peggiore**: 73.96% delle celle dell'AOI in allerta insieme (2026-07-08)
- **FAR per giornata-cella**: 99.99% delle giornate-cella in allerta su celle che non hanno bruciato nelle 72 h seguenti
- **Preavviso medio**: 51.3 h

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

- Per causa: meteo sotto la soglia 51, terreno sotto la soglia 36.
- Per terra (CORINE): agricola 38, bosco e seminaturale 21, artificiale 20, acque 8.
- Per mese: 04: 16, 05: 2, 06: 33, 07: 18, 08: 17, 09: 1.

| Cella | Incendio | CORINE | FWI max | FWI norm. max | Terreno | Punteggio max | Causa |
|---|---|---|---:|---:|---:|---:|---|
| it-lombardia|137|10 | 2026-04-05 | 112 | 12.8 | 0.26 | 0.32 | 0.08 | terreno sotto la soglia |
| it-lombardia|137|11 | 2026-04-05 | 311 | 13.6 | 0.27 | 0.78 | 0.21 | terreno sotto la soglia |
| it-lombardia|137|12 | 2026-04-05 | 311 | 13.6 | 0.27 | 0.78 | 0.21 | terreno sotto la soglia |
| it-lombardia|138|10 | 2026-04-05 | 512 | 12.8 | 0.26 | 0.29 | 0.07 | terreno sotto la soglia |
| it-lombardia|138|11 | 2026-04-05 | 311 | 13.6 | 0.27 | 0.78 | 0.21 | terreno sotto la soglia |
| it-lombardia|138|12 | 2026-04-05 | 311 | 13.6 | 0.27 | 0.77 | 0.21 | terreno sotto la soglia |
| it-lombardia|139|11 | 2026-04-05 | 512 | 13.6 | 0.27 | 0.26 | 0.07 | terreno sotto la soglia |
| it-lombardia|139|12 | 2026-04-05 | 311 | 13.6 | 0.27 | 0.77 | 0.21 | terreno sotto la soglia |
| it-lombardia|50|112 | 2026-04-17 | 211 | 7.0 | 0.14 | 0.47 | 0.07 | meteo sotto la soglia |
| it-lombardia|50|113 | 2026-04-17 | 211 | 7.0 | 0.14 | 0.47 | 0.07 | meteo sotto la soglia |
| it-lombardia|51|112 | 2026-04-17 | 211 | 7.0 | 0.14 | 0.47 | 0.07 | meteo sotto la soglia |
| it-lombardia|51|113 | 2026-04-17 | 121 | 7.0 | 0.14 | 0.32 | 0.05 | meteo sotto la soglia |
| it-lombardia|178|151 | 2026-04-27 | 333 | 11.5 | 0.23 | 0.84 | 0.19 | meteo sotto la soglia |
| it-lombardia|178|152 | 2026-04-27 | 333 | 11.5 | 0.23 | 0.83 | 0.19 | meteo sotto la soglia |
| it-lombardia|179|151 | 2026-04-27 | 333 | 11.5 | 0.23 | 0.82 | 0.19 | meteo sotto la soglia |
| it-lombardia|179|152 | 2026-04-27 | 333 | 11.5 | 0.23 | 0.84 | 0.19 | meteo sotto la soglia |
| it-lombardia|50|114 | 2026-05-17 | 211 | 0.8 | 0.02 | 0.47 | 0.01 | meteo sotto la soglia |
| it-lombardia|51|114 | 2026-05-17 | 121 | 0.8 | 0.02 | 0.32 | 0.00 | meteo sotto la soglia |
| it-lombardia|50|115 | 2026-06-04 | 211 | 16.0 | 0.32 | 0.47 | 0.15 | terreno sotto la soglia |
| it-lombardia|52|112 | 2026-06-04 | 211 | 16.0 | 0.32 | 0.46 | 0.15 | terreno sotto la soglia |
| it-lombardia|52|113 | 2026-06-04 | 211 | 16.0 | 0.32 | 0.47 | 0.15 | terreno sotto la soglia |
| it-lombardia|52|114 | 2026-06-04 | 211 | 16.0 | 0.32 | 0.47 | 0.15 | terreno sotto la soglia |
| it-lombardia|85|152 | 2026-06-04 | 211 | 2.9 | 0.06 | 0.46 | 0.03 | meteo sotto la soglia |
| it-lombardia|85|153 | 2026-06-04 | 211 | 2.9 | 0.06 | 0.46 | 0.03 | meteo sotto la soglia |
| it-lombardia|85|154 | 2026-06-04 | 211 | 2.9 | 0.06 | 0.46 | 0.03 | meteo sotto la soglia |
| it-lombardia|86|152 | 2026-06-04 | 211 | 2.9 | 0.06 | 0.46 | 0.03 | meteo sotto la soglia |
| it-lombardia|86|153 | 2026-06-04 | 211 | 2.9 | 0.06 | 0.46 | 0.03 | meteo sotto la soglia |
| it-lombardia|86|154 | 2026-06-04 | 121 | 2.9 | 0.06 | 0.31 | 0.02 | meteo sotto la soglia |
| it-lombardia|87|133 | 2026-06-04 | 211 | 2.7 | 0.05 | 0.46 | 0.02 | meteo sotto la soglia |
| it-lombardia|87|134 | 2026-06-04 | 211 | 2.7 | 0.05 | 0.46 | 0.02 | meteo sotto la soglia |
| it-lombardia|87|135 | 2026-06-04 | 211 | 2.7 | 0.05 | 0.46 | 0.03 | meteo sotto la soglia |
| it-lombardia|87|152 | 2026-06-04 | 211 | 2.9 | 0.06 | 0.46 | 0.03 | meteo sotto la soglia |
| it-lombardia|87|153 | 2026-06-04 | 211 | 2.9 | 0.06 | 0.46 | 0.03 | meteo sotto la soglia |
| it-lombardia|87|154 | 2026-06-04 | 211 | 2.9 | 0.06 | 0.47 | 0.03 | meteo sotto la soglia |
| it-lombardia|88|133 | 2026-06-04 | 211 | 2.7 | 0.05 | 0.46 | 0.03 | meteo sotto la soglia |
| it-lombardia|88|134 | 2026-06-04 | 211 | 2.7 | 0.05 | 0.46 | 0.03 | meteo sotto la soglia |
| it-lombardia|88|135 | 2026-06-04 | 211 | 2.7 | 0.05 | 0.46 | 0.03 | meteo sotto la soglia |
| it-lombardia|89|133 | 2026-06-04 | 211 | 2.7 | 0.05 | 0.46 | 0.02 | meteo sotto la soglia |
| it-lombardia|89|134 | 2026-06-04 | 211 | 2.7 | 0.05 | 0.46 | 0.03 | meteo sotto la soglia |
| it-lombardia|89|135 | 2026-06-04 | 211 | 2.7 | 0.05 | 0.46 | 0.03 | meteo sotto la soglia |
| it-lombardia|91|136 | 2026-06-10 | 211 | 7.1 | 0.14 | 0.46 | 0.07 | meteo sotto la soglia |
| it-lombardia|91|137 | 2026-06-10 | 121 | 7.1 | 0.14 | 0.32 | 0.05 | meteo sotto la soglia |
| it-lombardia|92|136 | 2026-06-10 | 211 | 7.1 | 0.14 | 0.46 | 0.07 | meteo sotto la soglia |
| it-lombardia|92|137 | 2026-06-10 | 121 | 7.1 | 0.14 | 0.32 | 0.05 | meteo sotto la soglia |
| it-lombardia|110|75 | 2026-06-12 | 211 | 0.9 | 0.02 | 0.49 | 0.01 | meteo sotto la soglia |
| it-lombardia|110|76 | 2026-06-12 | 311 | 0.9 | 0.02 | 0.68 | 0.01 | meteo sotto la soglia |
| it-lombardia|111|75 | 2026-06-12 | 211 | 0.9 | 0.02 | 0.51 | 0.01 | meteo sotto la soglia |
| it-lombardia|111|76 | 2026-06-12 | 112 | 0.9 | 0.02 | 0.28 | 0.01 | meteo sotto la soglia |
| it-lombardia|112|76 | 2026-06-12 | 112 | 0.9 | 0.02 | 0.31 | 0.01 | meteo sotto la soglia |
| it-lombardia|90|136 | 2026-06-17 | 211 | 15.7 | 0.31 | 0.46 | 0.14 | terreno sotto la soglia |
| it-lombardia|90|137 | 2026-06-17 | 211 | 15.7 | 0.31 | 0.46 | 0.14 | terreno sotto la soglia |
| it-lombardia|105|86 | 2026-07-01 | 211 | 24.9 | 0.50 | 0.46 | 0.23 | terreno sotto la soglia |
| it-lombardia|105|87 | 2026-07-01 | 121 | 24.9 | 0.50 | 0.31 | 0.16 | terreno sotto la soglia |
| it-lombardia|106|86 | 2026-07-01 | 121 | 24.9 | 0.50 | 0.31 | 0.15 | terreno sotto la soglia |
| it-lombardia|106|87 | 2026-07-01 | 121 | 24.9 | 0.50 | 0.31 | 0.16 | terreno sotto la soglia |
| it-lombardia|106|88 | 2026-07-01 | 211 | 24.9 | 0.50 | 0.46 | 0.23 | terreno sotto la soglia |
| it-lombardia|95|133 | 2026-07-20 | 112 | 22.8 | 0.46 | 0.29 | 0.13 | terreno sotto la soglia |
| it-lombardia|95|134 | 2026-07-20 | 111 | 22.8 | 0.46 | 0.29 | 0.13 | terreno sotto la soglia |
| it-lombardia|96|133 | 2026-07-20 | 112 | 22.8 | 0.46 | 0.29 | 0.13 | terreno sotto la soglia |
| it-lombardia|96|134 | 2026-07-20 | 111 | 22.8 | 0.46 | 0.29 | 0.13 | terreno sotto la soglia |
| it-lombardia|97|133 | 2026-07-20 | 112 | 22.8 | 0.46 | 0.30 | 0.14 | terreno sotto la soglia |
| it-lombardia|97|134 | 2026-07-20 | 121 | 22.8 | 0.46 | 0.32 | 0.15 | terreno sotto la soglia |
| it-lombardia|107|87 | 2026-07-21 | 112 | 14.1 | 0.28 | 0.28 | 0.08 | terreno sotto la soglia |
| it-lombardia|152|76 | 2026-07-30 | 311 | 2.3 | 0.05 | 0.79 | 0.04 | meteo sotto la soglia |
| it-lombardia|152|77 | 2026-07-30 | 312 | 2.3 | 0.05 | 1.00 | 0.05 | meteo sotto la soglia |
| it-lombardia|152|78 | 2026-07-30 | 322 | 2.3 | 0.05 | 0.91 | 0.04 | meteo sotto la soglia |
| it-lombardia|153|76 | 2026-07-30 | 311 | 2.3 | 0.05 | 0.79 | 0.04 | meteo sotto la soglia |
| it-lombardia|153|77 | 2026-07-30 | 321 | 2.3 | 0.05 | 0.87 | 0.04 | meteo sotto la soglia |
| it-lombardia|153|78 | 2026-07-30 | 312 | 2.3 | 0.05 | 1.00 | 0.05 | meteo sotto la soglia |
| it-lombardia|175|69 | 2026-08-04 | 311 | 0.7 | 0.01 | 0.78 | 0.01 | meteo sotto la soglia |
| it-lombardia|175|70 | 2026-08-04 | 231 | 4.2 | 0.08 | 0.67 | 0.06 | meteo sotto la soglia |
| it-lombardia|176|68 | 2026-08-04 | 311 | 0.7 | 0.01 | 0.79 | 0.01 | meteo sotto la soglia |
| it-lombardia|176|69 | 2026-08-04 | 311 | 0.7 | 0.01 | 0.79 | 0.01 | meteo sotto la soglia |
| it-lombardia|176|70 | 2026-08-04 | 211 | 4.2 | 0.08 | 0.47 | 0.04 | meteo sotto la soglia |
| it-lombardia|177|68 | 2026-08-04 | 311 | 0.7 | 0.01 | 0.79 | 0.01 | meteo sotto la soglia |
| it-lombardia|177|69 | 2026-08-04 | 231 | 0.7 | 0.01 | 0.70 | 0.01 | meteo sotto la soglia |
| it-lombardia|177|70 | 2026-08-04 | 211 | 4.2 | 0.08 | 0.47 | 0.04 | meteo sotto la soglia |
| it-lombardia|130|68 | 2026-08-05 | 112 | 24.1 | 0.48 | 0.34 | 0.16 | terreno sotto la soglia |
| it-lombardia|131|68 | 2026-08-05 | 512 | 24.1 | 0.48 | 0.35 | 0.17 | terreno sotto la soglia |
| it-lombardia|132|68 | 2026-08-05 | 512 | 24.1 | 0.48 | 0.26 | 0.12 | terreno sotto la soglia |
| it-lombardia|133|65 | 2026-08-05 | 311 | 12.5 | 0.25 | 0.75 | 0.19 | terreno sotto la soglia |
| it-lombardia|133|66 | 2026-08-05 | 512 | 12.5 | 0.25 | 0.31 | 0.08 | terreno sotto la soglia |
| it-lombardia|133|67 | 2026-08-05 | 512 | 12.5 | 0.25 | 0.25 | 0.06 | terreno sotto la soglia |
| it-lombardia|133|68 | 2026-08-05 | 512 | 12.5 | 0.25 | 0.32 | 0.08 | terreno sotto la soglia |
| it-lombardia|117|175 | 2026-08-08 | 512 | 24.7 | 0.49 | 0.34 | 0.17 | terreno sotto la soglia |
| it-lombardia|125|28 | 2026-08-09 | 112 | 28.5 | 0.57 | 0.33 | 0.19 | terreno sotto la soglia |
| it-lombardia|49|112 | 2026-09-24 | 211 | 12.2 | 0.24 | 0.47 | 0.12 | terreno sotto la soglia |

## Provenienza

| | |
|---|---|
| generato | 2026-11-26T13:32:56+00:00 |
| commit | `626506428402e7df05320c5296a6e9009362d538` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1.1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_AOI` | `it-lombardia` |
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
