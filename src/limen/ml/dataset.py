"""Convert ``training_samples`` rows into the (X, y, group) arrays.

Heavy deps (numpy + pandas) are imported lazily so plain code paths
can ``import limen.ml.dataset`` without the `ml` group installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from limen.data.repos.training_samples_repo import TrainingSample

# Order matters — the booster's feature_names list is persisted to MLflow
# so the live engine projects bundles onto the same vector.
CANONICAL_FEATURES: tuple[str, ...] = (
    "static.susc_ispra",
    "static.iffi_density_500",
    "static.distance_to_iffi_m",
    "static.slope_deg",
    "static.twi",
    "static.curvature",
    "static.litho_weight",
    "static.pai_class_norm",
    "insar.velocity_mmy",
    "insar.accel_mmy2",
    "insar.scatterer_count",
    # Antecedent rainfall at the sample's (cell, time) — CERRA replay
    # (ml/rain_features.py). Absent (pre-enrichment rows) degrades to 0.
    "rain.rain_24h_mm",
    "rain.rain_72h_mm",
    "rain.rain_30d_mm",
    "rain.max_i_24h_mmh",
)


@dataclass(frozen=True, slots=True)
class TrainingMatrix:
    """X, y, groups (spatial block) + the ordered feature schema."""

    feature_names: tuple[str, ...]
    X: Any  # np.ndarray
    y: Any  # np.ndarray
    groups: tuple[str, ...]


def _flatten(features: dict[str, Any]) -> dict[str, float]:
    flat: dict[str, float] = {}
    for top, child in features.items():
        if isinstance(child, dict):
            for k, v in child.items():
                if v is None:
                    flat[f"{top}.{k}"] = 0.0
                else:
                    flat[f"{top}.{k}"] = float(v)
    return flat


def to_matrix(samples: list[TrainingSample]) -> TrainingMatrix:
    """Stack samples into the canonical ordered matrix."""
    import numpy as np

    rows: list[list[float]] = []
    labels: list[int] = []
    groups: list[str] = []
    for s in samples:
        flat = _flatten(s.features)
        rows.append([flat.get(name, 0.0) for name in CANONICAL_FEATURES])
        labels.append(int(s.label))
        groups.append(s.split_block)
    matrix_x = np.array(rows, dtype=float)
    labels_y = np.array(labels, dtype=int)
    return TrainingMatrix(
        feature_names=CANONICAL_FEATURES,
        X=matrix_x,
        y=labels_y,
        groups=tuple(groups),
    )


def prune_collinear(
    matrix: TrainingMatrix, *, threshold: float
) -> tuple[TrainingMatrix, list[tuple[str, str, float]]]:
    """Drop features whose |Pearson r| with an earlier feature exceeds
    ``threshold``. Canonical order is the priority: the first feature of
    a collinear pair survives. GBMs tolerate collinearity numerically,
    but it splits SHAP credit across twins and muddies the breakdown.

    Returns the pruned matrix + the dropped pairs ``(kept, dropped, r)``.
    """
    import numpy as np

    x = np.asarray(matrix.X, dtype=float)
    names = list(matrix.feature_names)
    # Zero-variance columns produce NaN correlations — treat as 0.
    with np.errstate(invalid="ignore"):
        corr = np.corrcoef(x, rowvar=False)
    corr = np.nan_to_num(corr, nan=0.0)

    dropped: list[tuple[str, str, float]] = []
    keep: list[int] = []
    for j in range(len(names)):
        twin = next(
            (i for i in keep if abs(corr[i, j]) > threshold),
            None,
        )
        if twin is None:
            keep.append(j)
        else:
            dropped.append((names[twin], names[j], float(corr[twin, j])))
    if not dropped:
        return matrix, []
    return (
        TrainingMatrix(
            feature_names=tuple(names[j] for j in keep),
            X=x[:, keep],
            y=matrix.y,
            groups=matrix.groups,
        ),
        dropped,
    )


__all__ = ["CANONICAL_FEATURES", "TrainingMatrix", "prune_collinear", "to_matrix"]
