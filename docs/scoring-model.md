# Modello di scoring (V1, deterministico)

§2.4 del documento di progetto. Il motore è una funzione pura di un
`CellFeatureBundle`; ogni parametro numerico vive in
[`hazards/landslide.yaml`](../src/limen/config/hazards/landslide.yaml)
ed è validato da
[`RegionalThresholds`](../src/limen/core/scoring/regional_thresholds.py).
Non esistono costanti hard-coded nel codice di scoring: ogni
peso/soglia/cutoff proviene dallo YAML.

## Componenti

Il punteggio di rischio per la cella `c` all'istante `t` è la
combinazione lineare pesata:

```
risk(c, t) = w_S · S(c) + w_M · M(c, t) + w_E · E(t) + w_F · F(t) + w_H · H
```

La componente idraulica **H** è ora **attiva** (alimentata dal mosaico
idraulica ISPRA servito via GeoServer). I pesi top-level di default sono
`(w_S, w_M, w_E, w_F, w_H) = (0.35, 0.40, 0.15, 0.07, 0.03)` e DEVONO
sommare a 1.0 — il loader Pydantic lo impone. Il peso della componente
idraulica (`hydrology`) è `0.03`.

La V1.5 attiva inoltre una componente cinematica **K** sulle celle con
copertura di sensori in-situ (velocità di spostamento + inverse-velocity
di Fukuzono); su quelle celle monitorate la formula si rinormalizza in
`risk = w_K · K + (1 - w_K) · (somma V1)` con `w_K` preso dallo YAML in
`kinematic.weights.k` (default 0.20). Sulle celle non monitorate K
rimane 0 e la formula si riduce alla somma pesata V1. Vedi `docs/iot.md`.

### S — componente statica

```
S(c) = w_iffi · norm(iffi_density_500) + w_slope · norm(slope)
      + w_pai · norm(PAI) + w_litho · litho_weight
```

I sotto-pesi stanno in `static.weights` e il loader impone che sommino a 1:

| Chiave YAML | Peso | Ingresso |
|-------------|------|----------|
| `susc_ispra` | 0.00 | suscettibilità ISPRA (non più un ingresso) |
| `iffi_density` | 0.375 | frane IFFI entro 500 m |
| `slope` | 0.30 | pendenza dal DTM |
| `pai` | 0.225 | classe di pericolosità PAI |
| `litho_weight` | 0.10 | peso litologico dalla carta geologica |

La suscettibilità ISPRA non entra più in S: GeoServer, che è la sorgente
dei dati statici, non la serve. Il suo vecchio peso 0.30 è stato ridistribuito
in proporzione su IFFI, pendenza e PAI. La chiave resta nello schema a 0.00,
quindi il termine c'è nel breakdown ma non sposta il punteggio.

Normalizzazioni:

* `pai_class_norm`, `litho_weight` → già in [0, 1]; solo clamp. Un
  ingresso mancante vale 0.
* `iffi_density_500` conta le frane IFFI entro **500 m dalla cella** (non
  dal centroide). La saturazione è configurabile nello YAML tramite
  `static.iffi_density_saturation` (default = 8) e non è più fissata
  hard-coded a 3.
* `slope` satura al valore YAML `static.slope_saturation_deg`
  (default 45°).

**Cosa alimenta `limen calibrate` (verificato sul codice il 2026-11-08).**
Il motore ricalcola S a ogni chiamata dai fattori per cella; non legge né
`cell_static_factors.s_static` né `norm_stats`. `limen calibrate` scrive
`s_static` (una copia di S, per audit e per le query) e le min/max per AOI
in `norm_stats` (per il report), e rieseguirlo lascia ogni punteggio identico
byte per byte (#122). `norm_stats_repo.fetch_for_aoi` non ha chiamanti; la
query del backtest seleziona `s_static` ma non lo passa al motore. L'unica
cosa di `limen calibrate` che arriva in produzione è
`refresh_exposure_norm()`: ricalcola `cell_static_factors.exposure_norm` con
il blocco `exposure` dello YAML, e quel valore pesa l'indice di attenzione
del rollup per comune. Non entra nel punteggio.

### M — componente meteo

```
M(c, t) = w_caine · norm(caine_excess) + w_api · api_factor
        + w_soil · soil_factor
```

I sotto-pesi di default sono `(0.45, 0.30, 0.25)`.

* **Eccesso Caine I/D** — Caine 1980, Brunetti et al. 2010, Peruccacci et
  al. 2017. `I_threshold(D) = α · D^(-β)`. I coefficienti `α` / `β` per
  macroregione stanno in `caine.macroregions.*`. Ricostruzione degli
  eventi (ispirata a Melillo et al. 2018): split su un intervallo secco
  di `no_rain_break_hours`, scarto degli eventi sotto `min_event_mm`.
  ```
  caine_excess = max(0, log10(I_event) - log10(I_threshold(D_event)))
  ```
  `norm(caine_excess) = clamp01(caine_excess / 1.0)` — una decade piena
  sopra soglia ⇒ 1.0.

  Legge di potenza e ricostruzione degli eventi stanno nel pacchetto
  [`rainfall-thresholds`](https://pypi.org/project/rainfall-thresholds/)
  (estratto da Limen, Apache-2.0); α, β e i parametri degli eventi restano
  in `landslide.yaml`.

  **Ri-taratura della soglia I/D sul catalogo e-ITALICA.** La soglia è
  stata ri-tarata fittando l'inviluppo inferiore T5 (approccio
  Peruccacci-style) sulle coppie intensità-durata misurate dai
  pluviometri, per macroregione:

  | Macroregione     | α     | β     |
  |------------------|-------|-------|
  | `italy_default`  | 7.19  | 0.568 |
  | `southern_italy` | 8.75  | 0.645 |
  | `central_italy`  | 7.95  | 0.608 |
  | `northern_italy` | 6.37  | 0.512 |

  In precedenza si usava `7.7 / 0.39` (Brunetti 2010), che lasciava circa
  il 36% delle frane reali sotto soglia.

  **Quale curva vale per quale AOI: `macroregion_by_aoi`.** Il blocco
  assegna ogni regione a una macroregione; lo stesso elenco vale per
  `caine`, `rain_floor` e `flood_forecast`. Il raggruppamento è quello con
  cui sono state fittate le curve su e-ITALICA, non l'ISTAT: Abruzzo e Molise
  stanno in `central_italy`. Un'AOI non elencata (una provincia, un bacino)
  ricade su `italy_default`. Fino alla #122 nessuno impostava la
  macroregione, e tutta l'Italia girava sulla curva generica.

  **Floor di pioggia — bypass del gate di suscettibilità (issue #20).**
  Un secondo inviluppo Caine, *più permissivo* del T5 operativo, definito in
  `rain_floor.macroregions.*` (T2, 2° percentile dei log-residui, α più basso
  → più eventi lo superano):

  | Macroregione     | α (T5) | α (floor T2) | β     |
  |------------------|--------|--------------|-------|
  | `italy_default`  | 7.19   | 4.30         | 0.568 |
  | `southern_italy` | 8.75   | 5.25         | 0.645 |
  | `central_italy`  | 7.95   | 4.75         | 0.608 |
  | `northern_italy` | 6.37   | 3.80         | 0.512 |

  Il floor è una **proprietà di correttezza**, non un guardrail: con la
  copertura nazionale il tiering per suscettibilità (usare `s_static` come
  maschera per decidere dove spendere il budget meteo/LLM) rischia un falso
  negativo sistematico sugli eventi di coda — pioggia eccezionale su una cella
  catalogata a bassa suscettibilità, spesso perché l'inventario IFFI è
  incompleto, non perché il versante sia stabile. La regola di pruning corretta
  non è «salta la cella se a bassa suscettibilità» ma «salta la cella *solo se*
  a bassa suscettibilità **E** sotto il floor». Il predicato puro
  `MultiFactorScoringEngine.is_rescued_by_floor(bundle) -> bool` esprime proprio
  questa condizione: `True` ⇒ la cella va valutata a prescindere dal tier.

  Il floor è **condizionato all'umidità antecedente** (sigmoide del fattore
  suolo 0–7 cm, stesso blocco `soil`): una cella deve avere `wetness ≥
  rain_floor.wetness_min` per essere ripescata, così pioggia identica ripesca
  una cella satura ma non una secca. Nessun floor «piatto» in mm — resta
  regionalizzato per macroregione come le soglie T5. Gli attuali α sono
  segnaposto (~0.6·α_T5) da ri-tarare su e-ITALICA come il blocco `caine`.

  > Nota di roadmap: oggi (2026-11-08) il predicato non ha chiamanti nel
  > workflow, e lo sweep valuta tutte le celle. Quando lo step di selezione
  > celle nazionale (tiering) verrà introdotto, dovrà valutare il meteo per `tier_alto ∪ {celle sopra
  > floor}`, non per `tier_alto` soltanto. Il predicato è già il punto di
  > innesto; il floor è definito *prima* del tiering, per guidarne il disegno.

* **Fattore API** — antecedent precipitation index di Kohler & Linsley
  1951, decadimento giornaliero `k = 0.95` di default, sigmoide
  sull'anomalia standardizzata rispetto alla baseline mensile per cella.
  Quando la baseline non è nota, si ricade su `api.baseline.fallback_mm`.

* **Fattore suolo** — sigmoide su `soil_moisture_0_to_7cm` di
  Open-Meteo, centro `0.30`, pendenza `12.0`. Input mancante ⇒ `0.5`
  (punto medio della sigmoide, neutro).

* **Pioggia su neve (`snow`)** — un bonus additivo su M, non un nuovo peso.
  Con un manto di almeno `ros_min_depth_m` (0.05 m), la pioggia delle
  ultime 24 h carica la neve e aggiunge acqua di fusione: il fattore sale
  linearmente fino a 1 a `ros_rain_scale_mm` (30 mm) e aggiunge al più
  `weight` (0.15) a M, che resta limitata a 1. Senza neve il fattore è 0 e
  il punteggio è quello senza il blocco.

* **Cumulata relativa al nodo (`cumulata`, opzionale, #243)** — un innesco
  alternativo a Caine: la pioggia delle ultime `window_hours` ore divisa per
  `saturazione` volte la pioggia di riferimento del nodo
  (`pioggia_riferimento_mm`, da `limen clima-pioggia`). Con `modo:
  sostituisce` prende il posto di Caine, con `massimo` vale il più alto dei
  due; una cella senza riferimento resta su Caine. **Oggi il blocco non è in
  `landslide.yaml`**: il motore di produzione usa solo Caine, e la cumulata
  si prova nel backtest.

### E — componente sismica

```
pga_local = max sugli eventi i con M ≥ min_magnitude di
              PGA_event_i · exp(-Δt_i / τ)
z(p)      = (p - pga_threshold_g) / pga_scale_g
E = (sigmoid(z(pga_local)) - sigmoid(z(pga_min_g)))
    / (1 - sigmoid(z(pga_min_g)))                  se pga_local ≥ pga_min_g
  = 0                                               altrimenti
```

`τ = 2 d`, finestra retrospettiva `7 d`, magnitudo minima 3.5,
`pga_threshold_g = pga_scale_g = 0.05 g`, `pga_min_g = 0.02 g`.

`pga_min_g` (#284) è lo scuotimento sotto cui la cella non conta come
scossa (~MMI V): sotto, E vale 0 e la PGA della cella non si salva in
`seismic_pga_cella`; sopra, la sigmoide è riscalata per partire da 0, senza
gradino. Prima la sigmoide nuda dava già 0,27 a una PGA infinitesima.

**Soglia di pioggia dopo un terremoto (`seismic.soglia_pioggia`, opzionale,
#441).** Con il blocco, un terremoto forte abbassa la soglia di Caine invece
di sommarsi al punteggio: `α` (e il riferimento della cumulata, se attiva)
si moltiplica per `1 − r`, con
`r = riduzione_max · max_i f(PGA_i) · exp(−Δt_i / memoria_giorni)` sugli
eventi degli ultimi `lookback_giorni`, e `f` è la curva di E. Vale anche per
il floor di pioggia. **Oggi il blocco non è in `landslide.yaml`**: la soglia
non sente i terremoti e i punteggi sono quelli senza la #441.

Il PGA per evento proviene dalla ShakeMap INGV quando disponibile
(Fase 2), altrimenti dallo stimatore nominale
`0.05 · 10^((mag - 4.5) / 1.5)` limitato a 1.0 g. L'upgrade
all'attenuazione GMPE arriva in un prompt successivo.

### F — amplificazione post-incendio

```
F(m, sev) = exp(-((m - 6)² / 50)) · (floor + (1 - floor) · sev)   se 0 ≤ m ≤ 24
          = 0                                                      altrimenti
```

`m` = mesi trascorsi dal perimetro EFFIS più recente che interseca
l'AOI. Campana centrata a 6 mesi, zero al di fuori della finestra
0–24 mesi.

**La severità modula l'ampiezza, non la forma** (#67). Un incendio di chioma
severo e una bruciatura di stoppie non lasciano il versante nello stesso
stato, ma il decorso temporale dell'idrofobicità è lo stesso: cambia quanto,
non quando.

`sev` viene dalla **densità** di potenza radiativa FIRMS dentro il perimetro
(`frp_sum_mw / area_ha`), normalizzata dalla rampa `post_fire.frp_*`. Non
dalla somma: misurato su 2.419 perimetri EFFIS italiani 2012–2024, la somma
correla con l'area a **0,63** e la densità a **0,26**, quindi la somma è in
gran parte un indicatore di *dimensione* del rogo — usarla come severità
direbbe che un incendio grande è per definizione severo. Il dNBR resta la
misura di riferimento, ma il suo endpoint Copernicus richiede una richiesta
manuale (`EffisClient.fetch_dnbr` è uno stub); la firma accetta un numero in
[0,1] e non si accorge di dove venga.

Due proprietà da tenere a mente:

* il moltiplicatore è **≤ 1 per costruzione**, quindi la severità può solo
  attenuare un allarme, mai inventarne uno;
* con `sev` non misurata (nessun perimetro, o perimetro senza area) o con
  `post_fire.severity_floor: 1.0` il fattore è **identico** a prima della
  #67 — nessun ricalibro è obbligato.

`severity_floor` è un **giudizio, non una misura**: servirebbe un truth set di
frane post-incendio per tararlo, e le frane innescate da pioggia su suolo
percorso dal fuoco sono troppo rare per assemblarlo oggi.

### H — componente idraulica

La componente idraulica è **attiva**: alimentata dal mosaico idraulica
ISPRA servito via GeoServer. Per ciascuna cella si ricava
`flood_hazard_norm` mappando le classi di pericolosità sulla scala
AA/P1..P4: pericolosità elevata → P3, media → P2, bassa → P1. Il peso
top-level `hydrology` è `0.03` (vedi `hazards/landslide.yaml`).

**Componente dinamica multi-sorgente (issue #8, attiva di default).** `H`
riceve un *uplift* additivo quando è **prevista** un'inondazione su una cella
in zona di pericolosità idraulica (disattivabile con
`ENABLE_FLOOD_FORECAST=false`).
L'uplift combina tre segnali previsionali, ognuno scalato dalla pericolosità
statica ISPRA:

* **pluviale** — pioggia prevista a 72 h (Open-Meteo forecast);
* **fluviale** — rapporto portata prevista / normale stagionale (Open-Meteo
  Flood API / GloFAS);
* **costiero** — segnale di mareggiata / altezza d'onda (Open-Meteo Marine API).

```
bonus = hazard_uplift · flood_hazard_norm · max(pluviale, fluviale, costiero)
H     = clamp01(flood_hazard_norm + bonus)
```

Parametri in `flood_forecast.*` (sigmoide pioggia per macroregione + soglia
portata). Nessun forecast ⇒ `bonus = 0` ⇒ `H` puramente statico (byte-identico
a V1). La pericolosità statica ISPRA non è modificata; l'uplift è deterministico,
puro, e ogni fonte esterna degrada in modo neutro (segnale assente ⇒ 0).
Modellazione idraulica 2D fuori scope.

## Classificazione

```yaml
classes:
  none:      [0.00, 0.15]
  low:       [0.15, 0.35]
  moderate:  [0.35, 0.55]
  high:      [0.55, 0.75]
  very_high: [0.75, 1.00]
```

Contigue, coprono `[0, 1]`. Il validatore Pydantic rifiuta gap o
sovrapposizioni.

## Gate di accettazione della calibrazione (§2.5)

`limen calibrate` scrive `s_static` per cella, persiste le statistiche
min/max per AOI in `norm_stats` e scrive il report in
`reports/calibrate_<aoi>.md` (nessuno dei due arriva al motore: vedi la
nota nella componente S).

Il gate **Pearson(`s_static`, suscettibilità ISPRA)** è **disattivato**:
`calibration.s_vs_ispra_correlation_min: null`. Con la suscettibilità ISPRA
fuori da S la correlazione non misura più niente, quindi il report la
riporta se ci sono i dati ma non fa fallire il comando. Con
`LIMEN_CALIBRATE_STRICT=1` resta fatale solo la mancanza di righe di
suscettibilità.

## Accettazione del backtest (§2.5)

`limen backtest` riproduce una finestra storica. Il truth set è
**e-ITALICA** (eventi datati); la pioggia antecedente nel backtest
proviene da **CERRA** (risoluzione 5.5 km). I target stanno in
`calibration.backtest`:

| Chiave YAML | Valore | Significato |
|-------------|--------|-------------|
| `hit_rate_min` | `null` | l'hit rate si riporta ma non è un gate (#243) |
| `far_max` | `null` | il FAR si riporta ma non è un gate (#122) |
| `lead_time_hours_min` | 18.0 | preavviso medio minimo, in ore |
| `discriminazione_min` | 2.0 | hit rate diviso la quota di celle in allerta |
| `carico_riferimento` | 0.05 | quota di celle in allerta a cui si confrontano due varianti |
| `comuni.finestra_ore` | 72.0 | il comune dev'essere ≥ Moderato nelle 72 h prima dell'evento |
| `comuni.carico_massimo` | 0.10 | al più il 10 % dei comuni-giorno in allerta |
| `comuni.obiettivo` | 0.90 | quota di eventi da cogliere a quel carico (#352) |

Perché hit rate e FAR non sono più gate: la pioggia è un segnale per nodo,
uguale su 80-120 celle, e anche un oracolo che accendesse solo i nodi con
una frana avrebbe a 1 km² un FAR del 95-99 % (#122). Un hit rate alto, da
solo, premia chi accende di più. Il gate è la **discriminazione**, come per
alluvione e incendio, e due varianti si confrontano sulle frane colte **a
parità di carico** (`carico_riferimento`), non alla soglia di classe. La
metrica per comune (#352) è lo stesso metro delle verifiche.

**Ogni percentuale di frane colte va letta con il carico accanto.** Sulla
Liguria di novembre 2019 (#122) il motore porta a `Moderate` il 75,6 %
delle frane con il 67 % delle ore-cella in allerta (rapporto 1,13), e in
una misura successiva il 90,8 % con il 70 % (rapporto 1,3): a `Moderate`
il motore quasi non discrimina, perché S basta da sola a portarci mezza
regione. A `High` coglie il 3,8 % delle frane con lo 0,08 % delle
ore-cella in allerta (≈ 50 volte il caso). La vecchia cifra «63–77 % delle
frane almeno `Moderate`» è vera, ma senza il carico non dice quanto il
motore sia affidabile.

La tempesta dell'ottobre 2018 nel Sud Italia è la regressione canonica —
vedi
[`docs/artifacts/backtest_oct_2018.md`](./artifacts/backtest_oct_2018.md)
per l'ultima esecuzione.

## Drop-in V2

Il confine del motore è
`score(bundle: CellFeatureBundle) -> RiskScore[ComponentBreakdown]`: `RiskScore`
è generico sul breakdown del pericolo, `ComponentBreakdown` è quello delle
frane.
Il modello ML V2 implementerà la stessa firma e consumerà gli stessi
bundle costruiti da `core/features/assembler.py`, cosicché lo scambio
dei motori sia una singola riga in `WorkflowDeps`.
