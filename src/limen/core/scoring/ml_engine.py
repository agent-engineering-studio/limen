"""V2 :class:`MLScoringEngine` — placeholder shape (full body in Stage C).

The class is defined here so :mod:`limen.core.scoring.resolver` can
import it unconditionally; the resolver catches load failures and
falls back to the V1 deterministic engine, so an unconfigured MLflow
registry does not break the runtime.

Stage C will replace the body with the real LightGBM + isotonic +
SHAP-backed implementation that loads its artefacts from the MLflow
Model Registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from limen.core.logging import get_logger
from limen.core.models.risk import (
    CellFeatureBundle,
    ComponentBreakdown,
    MeteoBreakdown,
    RiskScore,
    StaticBreakdown,
)
from limen.core.scoring.base import ScoringEngine
from limen.core.scoring.regional_thresholds import (
    ClassCutoffs,
    RegionalThresholds,
    load_regional_thresholds,
)

log = get_logger(__name__)


class MLScoringEngineLoadError(RuntimeError):
    """Raised when the model registry returns nothing — V1 fallback path."""


def _classify(score: float, cutoffs: ClassCutoffs) -> str:
    if score < cutoffs.low.lo:
        return "None"
    if score < cutoffs.moderate.lo:
        return "Low"
    if score < cutoffs.high.lo:
        return "Moderate"
    if score < cutoffs.very_high.lo:
        return "High"
    return "VeryHigh"


@dataclass(slots=True)
class _MLArtefacts:
    """Holds the loaded LightGBM booster + isotonic calibrator + SHAP explainer."""

    model_uri: str
    model_version: str
    booster: object
    calibrator: object | None
    explainer: object | None
    feature_names: list[str]


class MLScoringEngine(ScoringEngine):
    """V2 LightGBM-backed engine — same Protocol as V1.

    Instances are produced by :meth:`from_registry`. Until a model is
    promoted to the configured ``stage`` the loader raises
    :class:`MLScoringEngineLoadError` and the resolver falls back to V1.
    """

    def __init__(
        self,
        artefacts: _MLArtefacts,
        *,
        thresholds: RegionalThresholds | None = None,
    ) -> None:
        self._artefacts = artefacts
        self._t: RegionalThresholds = thresholds or load_regional_thresholds()

    @property
    def model_uri(self) -> str:
        return self._artefacts.model_uri

    @property
    def model_version(self) -> str:
        return self._artefacts.model_version

    # ------------------------------------------------------------------
    # Construction — loads artefacts from the MLflow registry.
    # ------------------------------------------------------------------
    @classmethod
    def from_registry(
        cls,
        *,
        tracking_uri: str,
        registered_model: str,
        stage: str,
        thresholds: RegionalThresholds | None = None,
    ) -> MLScoringEngine:
        try:
            import mlflow
            from mlflow.tracking import MlflowClient
        except ImportError as exc:
            raise MLScoringEngineLoadError(
                "mlflow not installed — install the `ml` dependency group"
            ) from exc

        mlflow.set_tracking_uri(tracking_uri)
        client = MlflowClient(tracking_uri=tracking_uri)
        try:
            versions = client.get_latest_versions(registered_model, stages=[stage])
        except Exception as exc:
            raise MLScoringEngineLoadError(
                f"MLflow registry lookup failed for {registered_model}@{stage}: {exc}"
            ) from exc
        if not versions:
            raise MLScoringEngineLoadError(
                f"No model versions in stage {stage!r} for {registered_model!r}"
            )
        version = versions[0]
        model_uri = f"models:/{registered_model}/{stage}"
        try:
            booster = mlflow.lightgbm.load_model(model_uri)
        except Exception as exc:
            raise MLScoringEngineLoadError(f"booster load failed: {exc}") from exc

        # Calibrator + SHAP explainer are logged as artefacts under the
        # same run. Best-effort: a missing artefact downgrades the
        # engine (raw probabilities + no SHAP), it does not crash.
        calibrator = _try_load_artifact(version.run_id, "calibrator.pkl")
        explainer = _try_load_artifact(version.run_id, "shap_explainer.pkl")
        feature_names = _try_load_feature_names(version.run_id) or []

        return cls(
            _MLArtefacts(
                model_uri=model_uri,
                model_version=str(version.version),
                booster=booster,
                calibrator=calibrator,
                explainer=explainer,
                feature_names=feature_names,
            ),
            thresholds=thresholds,
        )

    # ------------------------------------------------------------------
    # ScoringEngine interface
    # ------------------------------------------------------------------
    def score(self, bundle: CellFeatureBundle) -> RiskScore:
        """Predict the cell's probability and convert it into a RiskScore.

        Stage C will wire the real LightGBM predict + calibrator path
        here. For now we expose a numerically-honest *stub* that asks
        the loaded booster for ``predict(features_row)`` if it
        supports it, and otherwise returns a zero baseline. This keeps
        the Protocol contract testable end-to-end without a trained
        model.
        """
        feature_row = _bundle_to_feature_row(bundle, names=self._artefacts.feature_names)
        prob = _predict(self._artefacts, feature_row)
        prob_calibrated = _calibrate(self._artefacts, prob)
        level_str = _classify(prob_calibrated, self._t.classes)
        # The SHAP-backed breakdown lands in Stage C; the placeholder
        # echoes the raw inputs so the workflow's downstream nodes can
        # still see *something* meaningful.
        breakdown = ComponentBreakdown(
            s=_clamp01(prob_calibrated),
            m=0.0,
            e=0.0,
            f=0.0,
            h=0.0,
            static_terms=StaticBreakdown(
                susc_ispra=_clamp01(bundle.static.susc_ispra),
                iffi_density=0.0,
                slope=_clamp01_scaled(bundle.static.slope_deg, 45.0),
                pai=_clamp01(bundle.static.pai_class_norm),
                litho_weight=_clamp01(bundle.static.litho_weight),
            ),
            meteo_terms=MeteoBreakdown(
                caine_excess=0.0, caine_norm=0.0, api_factor=0.5, soil_factor=0.5
            ),
        )
        from limen.core.models.risk import RiskLevel

        return RiskScore(
            score=prob_calibrated,
            level=RiskLevel(level_str),
            breakdown=breakdown,
            model_version=self._artefacts.model_version,
        )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _clamp01(x: float | None) -> float:
    if x is None:
        return 0.0
    return max(0.0, min(1.0, float(x)))


def _clamp01_scaled(x: float | None, cap: float) -> float:
    if x is None or cap <= 0:
        return 0.0
    return _clamp01(float(x) / cap)


def _bundle_to_feature_row(bundle: CellFeatureBundle, *, names: list[str]) -> list[float]:
    """Project a bundle onto the ordered feature vector the model expects."""
    flat: dict[str, float] = {
        "static.susc_ispra": _clamp01(bundle.static.susc_ispra),
        "static.iffi_density_500": float(bundle.static.iffi_density_500 or 0.0),
        "static.slope_deg": float(bundle.static.slope_deg or 0.0),
        "static.pai_class_norm": _clamp01(bundle.static.pai_class_norm),
        "static.litho_weight": _clamp01(bundle.static.litho_weight),
        "static.twi": float(bundle.static.twi or 0.0),
        "static.curvature": float(bundle.static.curvature or 0.0),
    }
    if not names:
        # Resolver fallback path: no feature schema → uniform vector,
        # the model isn't trained anyway.
        return list(flat.values())
    return [float(flat.get(n, 0.0)) for n in names]


def _predict(artefacts: _MLArtefacts, row: list[float]) -> float:
    booster: Any = artefacts.booster
    try:
        import numpy as np
    except ImportError:  # pragma: no cover
        return 0.0
    arr = np.array([row], dtype=float)
    try:
        raw = booster.predict(arr)
    except Exception as exc:  # pragma: no cover — load was successful
        log.warning("ml.predict.failed", error=str(exc))
        return 0.0
    return float(raw[0]) if len(raw) else 0.0


def _calibrate(artefacts: _MLArtefacts, prob: float) -> float:
    calibrator: Any = artefacts.calibrator
    if calibrator is None:
        return _clamp01(prob)
    try:
        import numpy as np

        calibrated = calibrator.predict(np.array([prob], dtype=float))
        return _clamp01(float(calibrated[0]))
    except Exception as exc:  # pragma: no cover
        log.warning("ml.calibrate.failed", error=str(exc))
        return _clamp01(prob)


def _try_load_artifact(run_id: str, name: str) -> object | None:
    try:
        import pickle

        import mlflow
    except ImportError:
        return None
    try:
        local_path = mlflow.artifacts.download_artifacts(run_id=run_id, artifact_path=name)
        from pathlib import Path

        with Path(local_path).open("rb") as fh:
            obj: object = pickle.load(fh)
            return obj
    except Exception as exc:
        log.debug("ml.artifact.missing", name=name, error=str(exc))
        return None


def _try_load_feature_names(run_id: str) -> list[str] | None:
    try:
        import json

        import mlflow
    except ImportError:
        return None
    try:
        local_path = mlflow.artifacts.download_artifacts(
            run_id=run_id, artifact_path="feature_names.json"
        )
        from pathlib import Path

        return [str(x) for x in json.loads(Path(local_path).read_text())]
    except Exception:
        return None


__all__ = ["MLScoringEngine", "MLScoringEngineLoadError"]
