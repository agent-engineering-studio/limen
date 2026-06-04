# V2 ML engine & MLOps

Phase 10 ships the V2 ML stack alongside V1, NOT instead of it. The
deterministic V1 engine remains the champion (drives alerts and
persisted scores) until a ML challenger clears the promotion gate on
honest, leakage-free metrics.

## Engine selection

`SCORING__ENGINE=deterministic|ml` flips between engines.
`SCORING__MODE=champion_only|shadow` selects whether the *other* engine
runs in parallel as a shadow challenger:

| ENGINE | MODE | What runs |
|---|---|---|
| `deterministic` | `champion_only` | V1 only — **default** |
| `deterministic` | `shadow` | V1 drives alerts; ML logs to `model_runs` |
| `ml` | `champion_only` | V2 drives alerts |
| `ml` | `shadow` | V2 drives alerts; V1 logs to `model_runs` |

Resolution lives in `limen.core.scoring.resolver.resolve_scoring_engine`.
If the MLflow registry doesn't have a Production model the resolver
**falls back to V1** and logs `scoring.ml_load_failed_fallback` — the
deterministic baseline is always live.

## Training pipeline (`limen train`)

```
training_samples (point-in-time correct, with split_block)
        │
        ▼
spatial-block CV folds (deterministic round-robin)
        │
        ▼
Optuna TPE over LightGBM hyperparams (objective = AUC-PR)
        │
        ▼
final LightGBM model on all data + booster log
        │
        ▼
isotonic calibration on OOF predictions  →  calibrator.pkl
        │
        ▼
SHAP TreeExplainer on the final booster   →  shap_explainer.pkl
        │
        ▼
MLflow run: params + metrics + model + artefacts
        │
        ▼
MLflow Model Registry: registered_model with `promoted` tag
```

* Spatial-block CV (never random) keeps autocorrelation between train
  and validation folds at zero — no leakage by construction.
* Class weights compensate the heavy 0/1 imbalance of landslide labels.
* Isotonic regression cuts Brier and gives operators well-calibrated
  probabilities.

## Promotion gate

Run via `limen train`. The promoted tag is set when EVERY clause holds:

* `auc_pr_mean ≥ SCORING__PROMOTION_AUC_PR_MIN` (default 0.55)
* `brier_calibrated ≤ SCORING__PROMOTION_BRIER_MAX` (default 0.20)
* `hit_rate@0.5 ≥ SCORING__PROMOTION_HIT_RATE_MIN` (default 0.70)
* `far@0.5 ≤ SCORING__PROMOTION_FAR_MAX` (default 0.30)
* `mean_lead_time_hours ≥ SCORING__PROMOTION_LEAD_TIME_HOURS_MIN` (default 18.0)
* **`ML AUC-PR > V1 baseline AUC-PR`** — ML must beat the deterministic
  baseline measured on the SAME spatial-block CV partition.

Promotion to a stage is then an **operator decision** (`mlflow models
transition-stage`), not an automatic action — even a passing gate
only marks the run as eligible.

## Champion-challenger shadow

The workflow inserts `ShadowChallengerExecutor` only when
`SCORING__MODE=shadow` and the resolver produced a challenger. The
executor:

1. Re-uses the same `assemble_bundles()` output the champion saw.
2. Scores each bundle with the challenger.
3. Writes one row per cell to `model_runs` with `role='challenger'`.
4. **Returns the context unchanged.** The champion's `cell_results` /
   `assessment` / alerts are the only authoritative outputs.

Persistence failures inside the shadow are swallowed (logged) — the
shadow branch is never allowed to abort the workflow.

## EGMS InSAR (V2.1)

`limen sync-egms` populates `cell_insar_features` (median velocity +
acceleration per cell, plus scatterer count + time envelope). Disabled
when `EGMS__BASE_URL` is empty. Cadence is yearly — APScheduler doesn't
own this; operators run it after each EGMS release.

## DL sub-model (V2.2)

`limen.ml.dl` ships a small 1D-CNN over a 1-week hourly rainfall
window. Trained offline (PyTorch, `dl` optional group), exported to
ONNX, and served via `onnxruntime` (in the `ml` group) by
`DLMeteoProbability`. Missing model OR missing onnxruntime → neutral
0.5 probability.

## Drift monitoring + retraining trigger

`enable_drift_monitoring=true` schedules `JOB_DRIFT_MONITOR` every
`MONITORING__DRIFT_CHECK_HOURS` (default 24h). One tick computes:

* **PSI** between the training distribution and recent live values;
* **KS** distance between the same;
* **Prediction drift** (absolute change in mean predicted probability).

A threshold breach OR enough new IFFI events triggers
`RetrainingTrigger(should_retrain=True, reason=...)`. The trigger
**only signals**; operators still run `limen train` and re-apply the
promotion gate manually.

## Where things live

| Path | Purpose |
|---|---|
| `src/limen/core/scoring/base.py` | `ScoringEngine` Protocol |
| `src/limen/core/scoring/resolver.py` | engine selection + shadow challenger |
| `src/limen/core/scoring/ml_engine.py` | V2 LightGBM-backed engine + MLflow loader |
| `src/limen/ml/feature_store.py` | offline sampler + spatial-block grid |
| `src/limen/ml/train.py` | Optuna + LightGBM + isotonic + SHAP + MLflow |
| `src/limen/ml/baseline.py` | V1 baseline scoring on training samples |
| `src/limen/ml/metrics.py` | AUC-PR / Brier / hit-rate-FAR / lead time |
| `src/limen/ml/dl/` | DL sub-model (model + train + serve) |
| `src/limen/ml/monitoring/` | drift primitives + RetrainingTrigger |
| `src/limen/integrations/egms/` | Copernicus EGMS InSAR sync |
| `src/limen/agents/executors/shadow_challenger.py` | shadow executor |
