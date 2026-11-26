# Limen backtest incendio — AOI `it-lombardia`

Finestra: **2026-01-01 → 2026-11-25**
Generato: 2026-11-26T15:00:36.279039+00:00
Pioggia della catena: **modello**
Soglia di allerta: **Moderate**, orizzonte di preavviso **72 h**

- Celle bruciate (perimetri EFFIS nella finestra): **109**
- Celle con almeno un'allerta: **34**
- Hit: **34**, mancati: **75** (celle bruciate); falsi allarmi: **1112270** giornate-cella

## Metriche §2.5

- **Hit rate**: 31.19%
- **Tasso di base**: 12.00% (quota di giornate in allerta a prescindere dagli incendi)
- **Discriminazione**: 2.60 volte il tasso di base
- **Carico meteo**: 9.94% delle giornate-nodo della stagione con FWI in fascia alta o oltre
- **Carico per cella**: 13.69% delle giornate-cella della stagione in allerta, su tutte le celle dell'AOI
- **Discriminazione spaziale**: 2.28 volte il carico per cella
- **Giorno peggiore**: 82.45% delle celle dell'AOI in allerta insieme (2026-07-09)
- **FAR per giornata-cella**: 99.99% delle giornate-cella in allerta su celle che non hanno bruciato nelle 72 h seguenti
- **Preavviso medio**: 56.5 h

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

- Per causa: meteo sotto la soglia 47, terreno sotto la soglia 27, cancello degli avvisi 1.
- Per terra (CORINE): agricola 36, artificiale 20, bosco e seminaturale 11, acque 8.
- Per mese: 04: 7, 05: 2, 06: 33, 07: 16, 08: 16, 09: 1.

| Cella | Incendio | CORINE | FWI max | FWI norm. max | Terreno | Punteggio max | Causa |
|---|---|---|---:|---:|---:|---:|---|
| it-lombardia|137|10 | 2026-04-05 | 112 | 12.8 | 0.37 | 0.32 | 0.12 | terreno sotto la soglia |
| it-lombardia|138|10 | 2026-04-05 | 512 | 12.8 | 0.37 | 0.29 | 0.11 | terreno sotto la soglia |
| it-lombardia|139|11 | 2026-04-05 | 512 | 13.6 | 0.39 | 0.26 | 0.10 | terreno sotto la soglia |
| it-lombardia|50|112 | 2026-04-17 | 211 | 7.0 | 0.20 | 0.47 | 0.09 | meteo sotto la soglia |
| it-lombardia|50|113 | 2026-04-17 | 211 | 7.0 | 0.20 | 0.47 | 0.09 | meteo sotto la soglia |
| it-lombardia|51|112 | 2026-04-17 | 211 | 7.0 | 0.20 | 0.47 | 0.09 | meteo sotto la soglia |
| it-lombardia|51|113 | 2026-04-17 | 121 | 7.0 | 0.20 | 0.32 | 0.06 | meteo sotto la soglia |
| it-lombardia|50|114 | 2026-05-17 | 211 | 0.8 | 0.02 | 0.47 | 0.01 | meteo sotto la soglia |
| it-lombardia|51|114 | 2026-05-17 | 121 | 0.8 | 0.02 | 0.32 | 0.01 | meteo sotto la soglia |
| it-lombardia|50|115 | 2026-06-04 | 211 | 16.0 | 0.46 | 0.47 | 0.21 | terreno sotto la soglia |
| it-lombardia|52|112 | 2026-06-04 | 211 | 16.0 | 0.46 | 0.46 | 0.21 | terreno sotto la soglia |
| it-lombardia|52|113 | 2026-06-04 | 211 | 16.0 | 0.46 | 0.47 | 0.21 | terreno sotto la soglia |
| it-lombardia|52|114 | 2026-06-04 | 211 | 16.0 | 0.46 | 0.47 | 0.22 | terreno sotto la soglia |
| it-lombardia|85|152 | 2026-06-04 | 211 | 2.9 | 0.08 | 0.46 | 0.04 | meteo sotto la soglia |
| it-lombardia|85|153 | 2026-06-04 | 211 | 2.9 | 0.08 | 0.46 | 0.04 | meteo sotto la soglia |
| it-lombardia|85|154 | 2026-06-04 | 211 | 2.9 | 0.08 | 0.46 | 0.04 | meteo sotto la soglia |
| it-lombardia|86|152 | 2026-06-04 | 211 | 2.9 | 0.08 | 0.46 | 0.04 | meteo sotto la soglia |
| it-lombardia|86|153 | 2026-06-04 | 211 | 2.9 | 0.08 | 0.46 | 0.04 | meteo sotto la soglia |
| it-lombardia|86|154 | 2026-06-04 | 121 | 2.9 | 0.08 | 0.31 | 0.03 | meteo sotto la soglia |
| it-lombardia|87|133 | 2026-06-04 | 211 | 2.7 | 0.08 | 0.46 | 0.04 | meteo sotto la soglia |
| it-lombardia|87|134 | 2026-06-04 | 211 | 2.7 | 0.08 | 0.46 | 0.04 | meteo sotto la soglia |
| it-lombardia|87|135 | 2026-06-04 | 211 | 2.7 | 0.08 | 0.46 | 0.04 | meteo sotto la soglia |
| it-lombardia|87|152 | 2026-06-04 | 211 | 2.9 | 0.08 | 0.46 | 0.04 | meteo sotto la soglia |
| it-lombardia|87|153 | 2026-06-04 | 211 | 2.9 | 0.08 | 0.46 | 0.04 | meteo sotto la soglia |
| it-lombardia|87|154 | 2026-06-04 | 211 | 2.9 | 0.08 | 0.47 | 0.04 | meteo sotto la soglia |
| it-lombardia|88|133 | 2026-06-04 | 211 | 2.7 | 0.08 | 0.46 | 0.04 | meteo sotto la soglia |
| it-lombardia|88|134 | 2026-06-04 | 211 | 2.7 | 0.08 | 0.46 | 0.04 | meteo sotto la soglia |
| it-lombardia|88|135 | 2026-06-04 | 211 | 2.7 | 0.08 | 0.46 | 0.04 | meteo sotto la soglia |
| it-lombardia|89|133 | 2026-06-04 | 211 | 2.7 | 0.08 | 0.46 | 0.04 | meteo sotto la soglia |
| it-lombardia|89|134 | 2026-06-04 | 211 | 2.7 | 0.08 | 0.46 | 0.04 | meteo sotto la soglia |
| it-lombardia|89|135 | 2026-06-04 | 211 | 2.7 | 0.08 | 0.46 | 0.04 | meteo sotto la soglia |
| it-lombardia|91|136 | 2026-06-10 | 211 | 7.1 | 0.20 | 0.46 | 0.09 | meteo sotto la soglia |
| it-lombardia|91|137 | 2026-06-10 | 121 | 7.1 | 0.20 | 0.32 | 0.07 | meteo sotto la soglia |
| it-lombardia|92|136 | 2026-06-10 | 211 | 7.1 | 0.20 | 0.46 | 0.09 | meteo sotto la soglia |
| it-lombardia|92|137 | 2026-06-10 | 121 | 7.1 | 0.20 | 0.32 | 0.07 | meteo sotto la soglia |
| it-lombardia|110|75 | 2026-06-12 | 211 | 0.9 | 0.03 | 0.49 | 0.01 | meteo sotto la soglia |
| it-lombardia|110|76 | 2026-06-12 | 311 | 0.9 | 0.03 | 0.68 | 0.02 | meteo sotto la soglia |
| it-lombardia|111|75 | 2026-06-12 | 211 | 0.9 | 0.03 | 0.51 | 0.01 | meteo sotto la soglia |
| it-lombardia|111|76 | 2026-06-12 | 112 | 0.9 | 0.03 | 0.28 | 0.01 | meteo sotto la soglia |
| it-lombardia|112|76 | 2026-06-12 | 112 | 0.9 | 0.03 | 0.31 | 0.01 | meteo sotto la soglia |
| it-lombardia|90|136 | 2026-06-17 | 211 | 15.7 | 0.45 | 0.46 | 0.21 | terreno sotto la soglia |
| it-lombardia|90|137 | 2026-06-17 | 211 | 15.7 | 0.45 | 0.46 | 0.21 | terreno sotto la soglia |
| it-lombardia|105|87 | 2026-07-01 | 121 | 24.9 | 0.71 | 0.31 | 0.22 | terreno sotto la soglia |
| it-lombardia|106|86 | 2026-07-01 | 121 | 24.9 | 0.71 | 0.31 | 0.22 | terreno sotto la soglia |
| it-lombardia|106|87 | 2026-07-01 | 121 | 24.9 | 0.71 | 0.31 | 0.22 | terreno sotto la soglia |
| it-lombardia|95|133 | 2026-07-20 | 112 | 22.8 | 0.65 | 0.29 | 0.19 | terreno sotto la soglia |
| it-lombardia|95|134 | 2026-07-20 | 111 | 22.8 | 0.65 | 0.29 | 0.19 | terreno sotto la soglia |
| it-lombardia|96|133 | 2026-07-20 | 112 | 22.8 | 0.65 | 0.29 | 0.19 | terreno sotto la soglia |
| it-lombardia|96|134 | 2026-07-20 | 111 | 22.8 | 0.65 | 0.29 | 0.19 | terreno sotto la soglia |
| it-lombardia|97|133 | 2026-07-20 | 112 | 22.8 | 0.65 | 0.30 | 0.20 | terreno sotto la soglia |
| it-lombardia|97|134 | 2026-07-20 | 121 | 22.8 | 0.65 | 0.32 | 0.21 | terreno sotto la soglia |
| it-lombardia|107|87 | 2026-07-21 | 112 | 14.1 | 0.40 | 0.28 | 0.11 | terreno sotto la soglia |
| it-lombardia|152|76 | 2026-07-30 | 311 | 2.3 | 0.07 | 0.79 | 0.05 | meteo sotto la soglia |
| it-lombardia|152|77 | 2026-07-30 | 312 | 2.3 | 0.07 | 1.00 | 0.07 | meteo sotto la soglia |
| it-lombardia|152|78 | 2026-07-30 | 322 | 2.3 | 0.07 | 0.91 | 0.06 | meteo sotto la soglia |
| it-lombardia|153|76 | 2026-07-30 | 311 | 2.3 | 0.07 | 0.79 | 0.05 | meteo sotto la soglia |
| it-lombardia|153|77 | 2026-07-30 | 321 | 2.3 | 0.07 | 0.87 | 0.06 | meteo sotto la soglia |
| it-lombardia|153|78 | 2026-07-30 | 312 | 2.3 | 0.07 | 1.00 | 0.07 | meteo sotto la soglia |
| it-lombardia|175|69 | 2026-08-04 | 311 | 0.7 | 0.02 | 0.78 | 0.02 | meteo sotto la soglia |
| it-lombardia|175|70 | 2026-08-04 | 231 | 4.2 | 0.12 | 0.67 | 0.08 | meteo sotto la soglia |
| it-lombardia|176|68 | 2026-08-04 | 311 | 0.7 | 0.02 | 0.79 | 0.02 | meteo sotto la soglia |
| it-lombardia|176|69 | 2026-08-04 | 311 | 0.7 | 0.02 | 0.79 | 0.02 | meteo sotto la soglia |
| it-lombardia|176|70 | 2026-08-04 | 211 | 4.2 | 0.12 | 0.47 | 0.06 | meteo sotto la soglia |
| it-lombardia|177|68 | 2026-08-04 | 311 | 0.7 | 0.02 | 0.79 | 0.02 | meteo sotto la soglia |
| it-lombardia|177|69 | 2026-08-04 | 231 | 0.7 | 0.02 | 0.70 | 0.01 | meteo sotto la soglia |
| it-lombardia|177|70 | 2026-08-04 | 211 | 4.2 | 0.12 | 0.47 | 0.06 | meteo sotto la soglia |
| it-lombardia|130|68 | 2026-08-05 | 112 | 24.1 | 0.69 | 0.34 | 0.23 | terreno sotto la soglia |
| it-lombardia|131|68 | 2026-08-05 | 512 | 24.1 | 0.69 | 0.35 | 0.24 | terreno sotto la soglia |
| it-lombardia|132|68 | 2026-08-05 | 512 | 24.1 | 0.69 | 0.26 | 0.18 | terreno sotto la soglia |
| it-lombardia|133|66 | 2026-08-05 | 512 | 12.5 | 0.36 | 0.31 | 0.11 | terreno sotto la soglia |
| it-lombardia|133|67 | 2026-08-05 | 512 | 12.5 | 0.36 | 0.25 | 0.09 | terreno sotto la soglia |
| it-lombardia|133|68 | 2026-08-05 | 512 | 12.5 | 0.36 | 0.32 | 0.11 | terreno sotto la soglia |
| it-lombardia|117|175 | 2026-08-08 | 512 | 24.7 | 0.71 | 0.34 | 0.24 | terreno sotto la soglia |
| it-lombardia|125|28 | 2026-08-09 | 112 | 28.5 | 0.82 | 0.33 | 0.27 | cancello degli avvisi |
| it-lombardia|49|112 | 2026-09-24 | 211 | 12.2 | 0.35 | 0.47 | 0.16 | terreno sotto la soglia |

## Provenienza

| | |
|---|---|
| generato | 2026-11-26T15:00:36+00:00 |
| commit | `89882ad5b11450cec70d66f6832298a095e64b98` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1.1` |
| flood | `flood-v1.4.0` |
| wildfire | `wildfire-v1.1.1` |
| comando | `limen backtest-wildfire` |
| `LIMEN_BACKTEST_WILDFIRE_AOI` | `it-lombardia` |
| `LIMEN_BACKTEST_WILDFIRE_END` | `2026-11-25` |
| `LIMEN_BACKTEST_WILDFIRE_LEVEL` | `Moderate` |
| `LIMEN_BACKTEST_WILDFIRE_START` | `2026-01-01` |
| `LIMEN_BACKTEST_WILDFIRE_TETTO` | `95:35:6-9` |
| `LIMEN_BACKUP_DIR` | `<percorso locale>` |
| `LIMEN_DATA_ROOT` | `<percorso locale>` |
| `LIMEN_DOMINIO` | `localhost` |
| `LIMEN_IMAGE_PREFIX` | `ghcr.io/agent-engineering-studio/limen-` |
| `LIMEN_IMAGE_TAG` | `sha-ecddbd8` |
| `LIMEN_IMPERVIOUSNESS_RASTER` | `<percorso locale>` |
| `LIMEN_PROXY_BIND` | `127.0.0.1` |
| `LIMEN_REPORTS_DIR` | `<percorso locale>` |
