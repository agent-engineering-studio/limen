"""V2 training pipeline (`limen train`).

End-to-end: fetch samples → spatial-block CV → Optuna AUC-PR tuning →
LightGBM fit with class weights → isotonic calibration → SHAP
explainer → MLflow tracking + Model Registry.

The function is designed to be safely callable on an empty dataset
(early-exit with a warning) so the CLI smoke tests can run on a freshly
migrated DB without IFFI seeded.
"""

from __future__ import annotations

import json
import pickle
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from limen.config.settings import Settings, get_settings
from limen.core.logging import get_logger
from limen.data.repos.training_samples_repo import (
    TrainingSample,
    fetch_samples,
    list_blocks,
)
from limen.ml.baseline import caine_baseline, v1_baseline
from limen.ml.dataset import CANONICAL_FEATURES, TrainingMatrix, to_matrix
from limen.ml.feature_store import spatial_block_folds
from limen.ml.metrics import auc_pr, brier_score, hit_rate_far, threshold_sweep, tss

_log: structlog.stdlib.BoundLogger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class TrainResult:
    """Headline outputs of one training run."""

    run_id: str | None
    model_version: str | None
    auc_pr_mean: float
    auc_pr_std: float
    brier_mean: float
    baseline_auc_pr: float
    promoted: bool


def _need_minimum_samples(samples: list[TrainingSample]) -> bool:
    """LightGBM needs both classes and at least a handful of rows."""
    if len(samples) < 20:
        return True
    labels = {int(s.label) for s in samples}
    return labels != {0, 1}


def _class_weight(y: Any) -> dict[int, float]:
    """Inverse-frequency weight to compensate the heavy 0/1 imbalance."""
    import numpy as np

    counts = np.bincount(y, minlength=2)
    total = counts.sum()
    return {
        0: float(total / (2.0 * max(counts[0], 1))),
        1: float(total / (2.0 * max(counts[1], 1))),
    }


def _objective_factory(
    matrix: TrainingMatrix,
    fold_blocks: list[list[str]],
) -> Any:
    """Build the Optuna objective — AUC-PR averaged across spatial folds."""
    import lightgbm as lgb
    import numpy as np
    import optuna
    from sklearn.metrics import average_precision_score

    block_to_fold = {b: i for i, fold in enumerate(fold_blocks) for b in fold}
    fold_idx = np.array([block_to_fold.get(g, 0) for g in matrix.groups])
    weights = _class_weight(matrix.y)

    def objective(trial: optuna.Trial) -> float:
        params: dict[str, Any] = {
            "objective": "binary",
            "metric": "average_precision",
            "verbosity": -1,
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            "num_leaves": trial.suggest_int("num_leaves", 15, 127),
            "min_data_in_leaf": trial.suggest_int("min_data_in_leaf", 5, 50),
            "feature_fraction": trial.suggest_float("feature_fraction", 0.6, 1.0),
            "bagging_fraction": trial.suggest_float("bagging_fraction", 0.6, 1.0),
            "bagging_freq": trial.suggest_int("bagging_freq", 0, 5),
            "lambda_l1": trial.suggest_float("lambda_l1", 0.0, 1.0),
            "lambda_l2": trial.suggest_float("lambda_l2", 0.0, 1.0),
            "n_estimators": trial.suggest_int("n_estimators", 100, 600),
            "scale_pos_weight": weights[1] / weights[0],
            "deterministic": True,
            "force_row_wise": True,
            "seed": 42,
        }
        aucs: list[float] = []
        for k in range(len(fold_blocks)):
            train_mask = fold_idx != k
            val_mask = fold_idx == k
            if val_mask.sum() == 0 or matrix.y[val_mask].sum() == 0:
                continue
            model = lgb.LGBMClassifier(**params)
            model.fit(matrix.X[train_mask], matrix.y[train_mask])
            proba = model.predict_proba(matrix.X[val_mask])[:, 1]
            aucs.append(float(average_precision_score(matrix.y[val_mask], proba)))
        return float(np.mean(aucs)) if aucs else 0.0

    return objective


def _cv_eval(
    matrix: TrainingMatrix, fold_blocks: list[list[str]], best_params: dict[str, Any]
) -> tuple[float, float, float, Any, Any]:
    """Run the final cross-validated evaluation with the tuned params.

    Returns ``(auc_pr_mean, auc_pr_std, brier_mean, oof_prob, oof_y)``.
    The out-of-fold probabilities + labels are the calibration training
    set for the isotonic regressor.
    """
    import lightgbm as lgb
    import numpy as np

    weights = _class_weight(matrix.y)
    block_to_fold = {b: i for i, fold in enumerate(fold_blocks) for b in fold}
    fold_idx = np.array([block_to_fold.get(g, 0) for g in matrix.groups])
    oof_prob = np.zeros(len(matrix.y), dtype=float)

    aucs: list[float] = []
    briers: list[float] = []
    for k in range(len(fold_blocks)):
        train_mask = fold_idx != k
        val_mask = fold_idx == k
        if val_mask.sum() == 0:
            continue
        params = dict(best_params)
        params.update(
            {
                "objective": "binary",
                "metric": "average_precision",
                "verbosity": -1,
                "scale_pos_weight": weights[1] / weights[0],
                "deterministic": True,
                "force_row_wise": True,
                "seed": 42,
            }
        )
        model = lgb.LGBMClassifier(**params)
        model.fit(matrix.X[train_mask], matrix.y[train_mask])
        proba = model.predict_proba(matrix.X[val_mask])[:, 1]
        oof_prob[val_mask] = proba
        if matrix.y[val_mask].sum() > 0:
            aucs.append(auc_pr(matrix.y[val_mask], proba))
            briers.append(brier_score(matrix.y[val_mask], proba))
    return (
        float(np.mean(aucs)) if aucs else 0.0,
        float(np.std(aucs)) if aucs else 0.0,
        float(np.mean(briers)) if briers else 0.0,
        oof_prob,
        matrix.y,
    )


def _check_promotion(
    *,
    settings: Settings,
    ml_auc_pr: float,
    ml_brier: float,
    baseline_auc_pr: float,
    hit_rate: float,
    far: float,
    lead_time_hours: float,
) -> bool:
    """Promotion gate — every floor must clear; ML must beat the baseline."""
    g = settings.scoring
    return (
        ml_auc_pr >= g.promotion_auc_pr_min
        and ml_brier <= g.promotion_brier_max
        and hit_rate >= g.promotion_hit_rate_min
        and far <= g.promotion_far_max
        and lead_time_hours >= g.promotion_lead_time_hours_min
        and ml_auc_pr > baseline_auc_pr
    )


async def run_training(*, settings: Settings | None = None) -> TrainResult:
    """End-to-end training entry point. Returns a :class:`TrainResult`.

    Idempotent in the sense that re-running with the same dataset
    deterministically produces the same metrics (seeds + folds are
    fixed). Missing optional deps degrade gracefully: with `ml` not
    installed the call returns early with a logged warning.
    """
    s = settings or get_settings()
    try:
        import mlflow
        import optuna
    except ImportError as exc:
        _log.warning(
            "training.skip.deps_missing",
            error=str(exc),
            hint="install the `ml` dependency group",
        )
        return TrainResult(
            run_id=None,
            model_version=None,
            auc_pr_mean=0.0,
            auc_pr_std=0.0,
            brier_mean=0.0,
            baseline_auc_pr=0.0,
            promoted=False,
        )

    samples = await fetch_samples()
    if _need_minimum_samples(samples):
        _log.warning("training.skip.too_few_samples", count=len(samples))
        return TrainResult(
            run_id=None,
            model_version=None,
            auc_pr_mean=0.0,
            auc_pr_std=0.0,
            brier_mean=0.0,
            baseline_auc_pr=0.0,
            promoted=False,
        )

    matrix = to_matrix(samples)
    blocks = await list_blocks()
    folds = spatial_block_folds(blocks, k=s.training.spatial_cv_folds, rng_seed=s.training.seed)

    mlflow.set_tracking_uri(s.scoring.mlflow_tracking_uri)
    mlflow.set_experiment(s.scoring.mlflow_experiment)
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    with mlflow.start_run() as run:
        mlflow.log_params(
            {
                "n_samples": len(samples),
                "positives": int(matrix.y.sum()),
                "spatial_blocks": len(blocks),
                "cv_folds": s.training.spatial_cv_folds,
                "optuna_trials": s.training.optuna_trials,
                "seed": s.training.seed,
            }
        )

        study = optuna.create_study(
            direction="maximize",
            sampler=optuna.samplers.TPESampler(seed=s.training.seed),
            study_name=f"limen-{run.info.run_id}",
        )
        objective = _objective_factory(matrix, folds)
        study.optimize(
            objective,
            n_trials=s.training.optuna_trials,
            timeout=s.training.optuna_timeout_seconds,
        )

        best_params = dict(study.best_params)
        mlflow.log_params({f"best_{k}": v for k, v in best_params.items()})

        auc_pr_mean, auc_pr_std, brier_mean, oof_prob, oof_y = _cv_eval(matrix, folds, best_params)

        baseline_scores = v1_baseline(samples)
        baseline_auc = auc_pr(matrix.y, baseline_scores)
        # Second reference: the bare Caine I-D power law — the ML must add
        # value over the triggering threshold itself, not just the blend.
        caine_scores = caine_baseline(samples)
        caine_auc = auc_pr(matrix.y, caine_scores)

        # Operational metrics at a sane default threshold (0.5 for probs).
        hit_rate, far = hit_rate_far(matrix.y, oof_prob, threshold=0.5)
        tss_05, _, spec_05 = tss(matrix.y, oof_prob, threshold=0.5)

        # Calibrator on the out-of-fold predictions.
        calibrator = _fit_isotonic(oof_prob, oof_y)
        calibrated = calibrator.transform(oof_prob)
        brier_calibrated = brier_score(matrix.y, calibrated)

        mlflow.log_metrics(
            {
                "auc_pr_mean": auc_pr_mean,
                "auc_pr_std": auc_pr_std,
                "brier_mean": brier_mean,
                "brier_calibrated": brier_calibrated,
                "baseline_auc_pr": baseline_auc,
                "caine_baseline_auc_pr": caine_auc,
                "hit_rate_at_0_5": hit_rate,
                "far_at_0_5": far,
                "tss_at_0_5": tss_05,
                "specificity_at_0_5": spec_05,
            }
        )
        # Operating points at 50/70/90% recall — what does catching X% of
        # the landslides cost, for the ML and both references?
        for label, scores in (
            ("ml", oof_prob),
            ("v1", baseline_scores),
            ("caine", caine_scores),
        ):
            for point in threshold_sweep(matrix.y, scores):
                r = int(point["recall_target"] * 100)
                mlflow.log_metrics(
                    {
                        f"{label}_far_at_r{r}": point.get("far", 1.0),
                        f"{label}_tss_at_r{r}": point.get("tss", 0.0),
                    }
                )

        # Fit the final model on ALL data using the best params + log it.
        import lightgbm as lgb

        final_params = dict(best_params)
        final_params.update(
            {
                "objective": "binary",
                "verbosity": -1,
                "scale_pos_weight": _class_weight(matrix.y)[1] / _class_weight(matrix.y)[0],
                "deterministic": True,
                "force_row_wise": True,
                "seed": s.training.seed,
            }
        )
        final_model = lgb.LGBMClassifier(**final_params)
        final_model.fit(matrix.X, matrix.y)

        mlflow.lightgbm.log_model(
            final_model.booster_,
            artifact_path="model",
            registered_model_name=s.scoring.mlflow_registered_model,
        )

        with tempfile.TemporaryDirectory() as tmpd:
            tmp = Path(tmpd)
            (tmp / "feature_names.json").write_text(json.dumps(list(CANONICAL_FEATURES)))
            with (tmp / "calibrator.pkl").open("wb") as fh:
                pickle.dump(calibrator, fh)
            explainer = _build_shap_explainer(final_model, matrix)
            if explainer is not None:
                with (tmp / "shap_explainer.pkl").open("wb") as fh:
                    pickle.dump(explainer, fh)
            for name in ("feature_names.json", "calibrator.pkl", "shap_explainer.pkl"):
                p = tmp / name
                if p.exists():
                    mlflow.log_artifact(str(p))

        # Lead time defaults to 0 unless we splice in the event times — the
        # honest answer until the dynamic feature window lands.
        promoted = _check_promotion(
            settings=s,
            ml_auc_pr=auc_pr_mean,
            ml_brier=brier_calibrated,
            baseline_auc_pr=baseline_auc,
            hit_rate=hit_rate,
            far=far,
            lead_time_hours=0.0,
        )
        mlflow.set_tag("promoted", str(promoted))

        _log.info(
            "training.done",
            run_id=run.info.run_id,
            n_samples=len(samples),
            auc_pr_mean=auc_pr_mean,
            baseline_auc_pr=baseline_auc,
            promoted=promoted,
        )

        return TrainResult(
            run_id=run.info.run_id,
            model_version=None,
            auc_pr_mean=auc_pr_mean,
            auc_pr_std=auc_pr_std,
            brier_mean=brier_calibrated,
            baseline_auc_pr=baseline_auc,
            promoted=promoted,
        )


def _fit_isotonic(y_prob: Any, y_true: Any) -> Any:
    from sklearn.isotonic import IsotonicRegression

    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(y_prob, y_true)
    return iso


def _build_shap_explainer(model: Any, matrix: TrainingMatrix) -> Any | None:  # noqa: ARG001
    try:
        import shap
    except ImportError:
        return None
    try:
        # Sample to a manageable size — SHAP TreeExplainer doesn't need
        # the full matrix for the model class.
        return shap.TreeExplainer(model)
    except Exception as exc:  # pragma: no cover
        _log.debug("training.shap.skip", error=str(exc))
        return None


__all__ = ["TrainResult", "run_training"]
