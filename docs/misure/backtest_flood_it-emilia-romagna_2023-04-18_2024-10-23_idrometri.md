# Backtest alluvione — AOI `it-emilia-romagna`

Finestra: **2023-04-18 → 2024-10-23**
Generato: 2026-11-12T13:52:31+00:00
Soglie: `flood-v1.3.0` (40-120 mm/72 h)

Ramo fluviale: portata GloFAS su **95 nodi su 123**.

Idrometri Arpae (CC BY 4.0, Arpae Emilia-Romagna) su **84 nodi**: il rapporto di portata è `max(GloFAS, idrometro del giorno prima)`, con la rampa dell'idrometro da 2 a 5 volte la piena ordinaria sopra il fondo (#501).

Cancello sotto «Alto»: suscettibilità ≥ 0.50 (`alerts.min_predisposition`), come negli avvisi spediti.

## Truth set

- Fonte: **Copernicus Emergency Management Service — Rapid Mapping**
- Licenza: © European Union, Copernicus EMS. Free to use with attribution.
- Credenziali richieste: **none**
- Geometria: observedEventA (estensione osservata), non areaOfInterest
- Copertura: Il visore pubblico espone le attivazioni dal 2023; quelle precedenti non hanno un'API documentata.

> **Limite noto.** La delineazione satellitare è un limite inferiore: allagamenti urbani brevi o sotto chioma possono non comparire, quindi un falso allarme misurato qui può essere un evento non visto.

| Attivazione | Data evento | Poligoni | Area allagata (km²) |
|---|---|---:|---:|
| `EMSR659` | 2023-05-02 | 1232 | 75.4 |
| `EMSR664` | 2023-05-16 | 6385 | 550.1 |
| `EMSR705` | 2023-11-02 | 1397 | 41.0 |
| `EMSR721` | 2024-05-14 | 222 | 1.3 |
| `EMSR762` | 2024-09-18 | 1070 | 73.8 |
| `EMSR771` | 2024-10-20 | 3177 | 225.9 |
| `EMSR795` | 2025-03-14 | 566 | 19.0 |
| `EMSR800` | 2025-04-17 | 40 | 0.3 |
| `EMSR843` | 2025-09-22 | 258 | 0.7 |
| `EMSR855` | 2026-01-06 | 130 | 2.4 |
| `EMSR858` | 2026-01-20 | 373 | 5.1 |
| `EMSR871` | 2026-03-31 | 1015 | 33.5 |

## Metriche

| Replica | Dal | Hit rate | Tasso di base | Rapporto | FAR | Preavviso | Giorni-cella (veri/falsi/non verif.) | Avvisi |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `issued` | 2024-09-04 | 90% | 28% | 3.16x | 86% | 51 h | 2437 / 15206 / 22913 | 12872 |
| `observed` | 2024-09-04 | 78% | 29% | 2.71x | 87% | 55 h | 2267 / 14623 / 23139 | 11147 |

Le due repliche sono misurate sulla **stessa finestra**, altrimenti non sarebbero confrontabili: l'archivio delle previsioni emesse comincia nel febbraio 2024, e senza il taglio `observed` includerebbe eventi che `issued` non può vedere. Con `LIMEN_BACKTEST_FLOOD_MODE=observed` da sola la finestra resta intera e copre tutto il catalogo.

`issued` è la previsione **come fu emessa** — la skill operativa. `observed` è la pioggia poi caduta: il tetto con una previsione perfetta, non un risultato. La distanza fra le due dice se conviene ritarare le soglie o migliorare il dato in ingresso.

Il **tasso di base** è la quota di giornate in cui una cella poi allagata era in allerta comunque: è il metro dell'hit rate, e il rapporto fra i due è quanto il modello discrimina davvero.

Il **FAR è per cella-giorno di allerta**: è il carico che un operatore sopporta davvero, e non ha i bordi sbagliati dell'episodio — un'allerta accesa per diciotto giorni è un episodio che comincia il primo, e l'evento del diciassettesimo cadrebbe fuori dalle sue 72 h.

**Ambito.** Sono valutate solo le celle allagate e quelle dentro una maschera di osservazione: una cella che non è né l'una né l'altra produce solo giorni non verificabili, già fuori da ogni denominatore, quindi escluderla non cambia nessuna metrica.

Un giorno di allerta entra nel FAR solo se **qualcuno ha guardato**: dentro una maschera di osservazione EMS l'assenza di poligono allagato è un "non allagato" osservato, fuori non è informazione. Gli episodi *non verificabili* restano contati e fuori dal denominatore, come `non verificabile` nel protocollo FAR degli alert. Contarli fra i falsi darebbe un FAR del 100% ogni volta che il satellite ha mappato una frazione dell'area allertata.

### Per cella (CSI)

| Replica | CSI | POD | FAR per cella | Bias | Hit / mancati / falsi | Allertate non osservate |
|---|---:|---:|---:|---:|---:|---:|
| `issued` | 16% | 90% | 83% | 5.39 | 1055 / 120 / 5281 | 643 |
| `observed` | 16% | 78% | 83% | 4.72 | 921 / 254 / 4630 | 701 |

La stessa tabella di contingenza con cui `copernicus-ems` misura le mappe satellitari, ma per **cella** sull'intera finestra: hit e mancati sono quelli dell'hit rate (il POD coincide), un **falso** è una cella non allagata con almeno un'allerta smentita da un passaggio, e le celle allertate che nessun passaggio ha verificato restano a parte, mai fra i falsi. Il FAR per cella non è quello per cella-giorno della tabella sopra: conta le celle, non il carico. Bias > 1 vuol dire più celle allertate che allagate. Il CSI non entra nel gate §2.5.

### Gate §2.5

- `issued`: hit rate PASS, FAR FAIL, preavviso PASS
- `observed`: hit rate PASS, FAR FAIL, preavviso PASS

- `issued` (dal 2024-09-04): 1175 celle di verità, 7236 celle valutate su 36 giorni, 1055 hit / 120 mancati; 12872 avvisi distinti (14148 da pioggia, 26408 da portata; 0 giornate-cella fermate dal cancello), 17643 giorni-cella verificabili su 40556.
- `observed` (dal 2024-09-04): 1175 celle di verità, 7236 celle valutate su 36 giorni, 921 hit / 254 mancati; 11147 avvisi distinti (13744 da pioggia, 26285 da portata; 0 giornate-cella fermate dal cancello), 16890 giorni-cella verificabili su 40029.

## Provenienza

| | |
|---|---|
| generato | 2026-11-12T13:52:31+00:00 |
| commit | `834799ea674fea1e88bcec9a5efe02392e5dbb89` |
| limen | 0.1.0 |
| landslide | `limen-deterministic-v1` |
| flood | `flood-v1.3.0` |
| wildfire | `wildfire-v1.1.0` |
| comando | `-c` |
| `LIMEN_BACKTEST_FLOOD_AOI` | `it-emilia-romagna` |
| `LIMEN_BACKTEST_FLOOD_IDROMETRI` | `arpae` |
| `LIMEN_REPORTS_DIR` | `<percorso locale>` |
