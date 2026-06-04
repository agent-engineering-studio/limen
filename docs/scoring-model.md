# Scoring model (V1, deterministic)

§2.4 of the project doc. The engine is a pure function of a
`CellFeatureBundle`; every numeric knob lives in
[`regional_thresholds.yaml`](../src/limen/config/regional_thresholds.yaml)
and is validated by
[`RegionalThresholds`](../src/limen/core/scoring/regional_thresholds.py).

## Components

The risk score for cell `c` at time `t` is the weighted linear
combination:

```
risk(c, t) = w_S · S(c) + w_M · M(c, t) + w_E · E(t) + w_F · F(t) + w_H · H
```

`H = 0` in V1 (hydrology lands later). Top-level weights default to
`(w_S, w_M, w_E, w_F, w_H) = (0.35, 0.40, 0.15, 0.07, 0.03)` and MUST
sum to 1.0 — the Pydantic loader enforces this.

V1.5 additionally activates a kinematic component **K** on cells with
in-situ sensor coverage (displacement velocity + Fukuzono
inverse-velocity); on those monitored cells the formula renormalises to
`risk = w_K · K + (1 - w_K) · (V1 sum)` with `w_K` from the YAML's
`kinematic.weights.k` (default 0.20). On unmonitored cells K stays 0
and the formula reduces to the V1 weighted sum. See `docs/iot.md`.

### S — static component

```
S(c) = w_susc · norm(susc_ISPRA) + w_iffi · norm(iffi_density_500)
      + w_slope · norm(slope) + w_pai · norm(PAI) + w_litho · litho_weight
```

Sub-weights default `(0.30, 0.25, 0.20, 0.15, 0.10)` and sum to 1.

Normalisations:

* `susc_ispra`, `pai_class_norm`, `litho_weight` → already in [0, 1];
  clamp-only.
* `iffi_density_500` saturates at 3 features per 500 m buffer (internal
  cap; not a tunable knob — the §2.4 paper allows >1 here).
* `slope` saturates at the YAML's `static.slope_saturation_deg`
  (default 45°).

`s_static` is precomputed once per AOI by `limen calibrate` and stored
in `cell_static_factors.s_static` for cheap reads at scoring time.

### M — meteo component

```
M(c, t) = w_caine · norm(caine_excess) + w_api · api_factor
        + w_soil · soil_factor
```

Sub-weights default `(0.45, 0.30, 0.25)`.

* **Caine I/D excess** — Caine 1980, Brunetti et al. 2010, Peruccacci et
  al. 2017. `I_threshold(D) = α · D^(-β)`. Per-macroregion `α` / `β` in
  `caine.macroregions.*`. Event reconstruction (Melillo et al. 2018
  inspired): split on a dry run of `no_rain_break_hours`, drop events
  below `min_event_mm`.
  ```
  caine_excess = max(0, log10(I_event) - log10(I_threshold(D_event)))
  ```
  `norm(caine_excess) = clamp01(caine_excess / 1.0)` — one full decade
  above threshold ⇒ 1.0.

* **API factor** — Kohler & Linsley 1951 antecedent precipitation
  index, daily decay `k = 0.95` by default, sigmoid over the
  standardised anomaly vs the per-cell monthly baseline. When the
  baseline is unknown, fall back to `api.baseline.fallback_mm`.

* **Soil factor** — sigmoid over Open-Meteo `soil_moisture_0_to_7cm`,
  centre `0.30`, steepness `12.0`. Missing input ⇒ `0.5` (sigmoid
  midpoint, neutral).

### E — seismic component

```
pga_local = max over events i with M ≥ min_magnitude of
              PGA_event_i · exp(-Δt_i / τ)
E = sigmoid((pga_local - pga_threshold_g) / pga_scale_g)   if pga_local > 0
  = 0                                                       otherwise
```

`τ = 2 d`, lookback `7 d`, `pga_threshold_g = pga_scale_g = 0.05 g`.

The per-event PGA comes from INGV ShakeMap when available (Phase 2),
otherwise from the nominal estimator
`0.05 · 10^((mag - 4.5) / 1.5)` clipped at 1.0 g. The GMPE attenuation
upgrade lands in a later prompt.

### F — post-fire amplification

```
F(m) = exp(-((m - 6)² / 50))    if 0 ≤ m ≤ 24
     = 0                         otherwise
```

`m` = months since the most recent EFFIS perimeter intersecting the
AOI. Bell centred at 6 months, zero outside the 0–24 month window.

### H — hydrology

`H = 0` in V1. Placeholder for V1.5 (groundwater, river levels).

## Classification

```yaml
classes:
  none:      [0.00, 0.15]
  low:       [0.15, 0.35]
  moderate:  [0.35, 0.55]
  high:      [0.55, 0.75]
  very_high: [0.75, 1.00]
```

Contiguous, covering `[0, 1]`. The Pydantic validator rejects gaps or
overlaps.

## Calibration acceptance gate (§2.5)

`limen calibrate` writes `s_static` per cell, persists per-AOI min/max
`norm_stats`, and checks **Pearson(`s_static`, ISPRA susceptibility) ≥
0.85**. Failing the gate exits with code `1` and prints the report
under `reports/calibrate_<aoi>.md`. When ISPRA susceptibility isn't
ingested per-cell yet (V1 pilot), the gate logs and skips by default;
set `LIMEN_CALIBRATE_STRICT=1` to make missing data fatal.

## Backtest acceptance (§2.5)

`limen backtest` replays a historical window using Open-Meteo ERA5 +
IFFI as the truth set. Targets:

* **Hit rate** ≥ 70%
* **FAR** ≤ 30%
* **Mean lead time** ≥ 18 h

The Oct 2018 Southern-Italy storm is the canonical regression — see
[`docs/artifacts/backtest_oct_2018.md`](./artifacts/backtest_oct_2018.md)
for the latest run.

## V2 drop-in

The engine boundary is `score(bundle: CellFeatureBundle) -> RiskScore`.
The V2 ML model will implement the same signature and consume the same
bundles built by `core/features/assembler.py`, so swapping engines is a
single line in `WorkflowDeps`.
