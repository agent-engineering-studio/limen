# Modello di scoring (V1, deterministico)

§2.4 del documento di progetto. Il motore è una funzione pura di un
`CellFeatureBundle`; ogni parametro numerico vive in
[`regional_thresholds.yaml`](../src/limen/config/regional_thresholds.yaml)
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
S(c) = w_susc · norm(susc_ISPRA) + w_iffi · norm(iffi_density_500)
      + w_slope · norm(slope) + w_pai · norm(PAI) + w_litho · litho_weight
```

I sotto-pesi di default sono `(0.30, 0.25, 0.20, 0.15, 0.10)` e sommano
a 1.

Normalizzazioni:

* `susc_ispra`, `pai_class_norm`, `litho_weight` → già in [0, 1];
  solo clamp.
* `iffi_density_500` conta le frane IFFI entro **500 m dalla cella** (non
  dal centroide). La saturazione è configurabile nello YAML tramite
  `static.iffi_density_saturation` (default = 8) e non è più fissata
  hard-coded a 3.
* `slope` satura al valore YAML `static.slope_saturation_deg`
  (default 45°).

`s_static` è precalcolato una volta per AOI da `limen calibrate` e
memorizzato in `cell_static_factors.s_static` per letture rapide al
momento dello scoring.

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

  **Ri-taratura della soglia I/D sul catalogo e-ITALICA.** La soglia è
  stata ri-tarata fittando l'inviluppo inferiore T5 (approccio
  Peruccacci-style) sulle coppie intensità-durata misurate dai
  pluviometri, per macroregione:

  | Macroregione   | α     | β     |
  |----------------|-------|-------|
  | `italy_default`| 7.19  | 0.568 |
  | `southern`     | 8.75  | 0.645 |
  | `central`      | 7.95  | 0.608 |
  | `northern`     | 6.37  | 0.512 |

  In precedenza si usava `7.7 / 0.39` (Brunetti 2010), che lasciava circa
  il 36% delle frane reali sotto soglia.

* **Fattore API** — antecedent precipitation index di Kohler & Linsley
  1951, decadimento giornaliero `k = 0.95` di default, sigmoide
  sull'anomalia standardizzata rispetto alla baseline mensile per cella.
  Quando la baseline non è nota, si ricade su `api.baseline.fallback_mm`.

* **Fattore suolo** — sigmoide su `soil_moisture_0_to_7cm` di
  Open-Meteo, centro `0.30`, pendenza `12.0`. Input mancante ⇒ `0.5`
  (punto medio della sigmoide, neutro).

### E — componente sismica

```
pga_local = max sugli eventi i con M ≥ min_magnitude di
              PGA_event_i · exp(-Δt_i / τ)
E = sigmoid((pga_local - pga_threshold_g) / pga_scale_g)   se pga_local > 0
  = 0                                                        altrimenti
```

`τ = 2 d`, finestra retrospettiva `7 d`,
`pga_threshold_g = pga_scale_g = 0.05 g`.

Il PGA per evento proviene dalla ShakeMap INGV quando disponibile
(Fase 2), altrimenti dallo stimatore nominale
`0.05 · 10^((mag - 4.5) / 1.5)` limitato a 1.0 g. L'upgrade
all'attenuazione GMPE arriva in un prompt successivo.

### F — amplificazione post-incendio

```
F(m) = exp(-((m - 6)² / 50))    se 0 ≤ m ≤ 24
     = 0                         altrimenti
```

`m` = mesi trascorsi dal perimetro EFFIS più recente che interseca
l'AOI. Campana centrata a 6 mesi, zero al di fuori della finestra
0–24 mesi.

### H — componente idraulica

La componente idraulica è **attiva**: alimentata dal mosaico idraulica
ISPRA servito via GeoServer. Per ciascuna cella si ricava
`flood_hazard_norm` mappando le classi di pericolosità sulla scala
AA/P1..P4: pericolosità elevata → P3, media → P2, bassa → P1. Il peso
top-level `hydrology` è `0.03` (vedi `regional_thresholds.yaml`).

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
min/max per AOI in `norm_stats`, e verifica
**Pearson(`s_static`, suscettibilità ISPRA) ≥ 0.85**. Il fallimento del
gate esce con codice `1` e stampa il report in
`reports/calibrate_<aoi>.md`. Quando la suscettibilità ISPRA non è ancora
ingerita per-cella (pilota V1), il gate logga e salta di default;
impostare `LIMEN_CALIBRATE_STRICT=1` per rendere fatale il dato mancante.

## Accettazione del backtest (§2.5)

`limen backtest` riproduce una finestra storica. Il truth set è
**e-ITALICA** (eventi datati); la pioggia antecedente nel backtest
proviene da **CERRA** (risoluzione 5.5 km). Target:

* **Hit rate** ≥ 70%
* **FAR** ≤ 30%
* **Lead time medio** ≥ 18 h

Su ground-truth reale, circa il **63–77%** delle frane raggiunge almeno
il livello `Moderate`; il FAR resta limitato dall'incompletezza del
catalogo.

La tempesta dell'ottobre 2018 nel Sud Italia è la regressione canonica —
vedi
[`docs/artifacts/backtest_oct_2018.md`](./artifacts/backtest_oct_2018.md)
per l'ultima esecuzione.

## Drop-in V2

Il confine del motore è `score(bundle: CellFeatureBundle) -> RiskScore`.
Il modello ML V2 implementerà la stessa firma e consumerà gli stessi
bundle costruiti da `core/features/assembler.py`, cosicché lo scambio
dei motori sia una singola riga in `WorkflowDeps`.
