"""Honest metrics for the training pipeline + the promotion gate.

* :func:`auc_pr` — area under the precision-recall curve (the §2.6
  primary objective). Robust to the heavy class imbalance landslide
  datasets have.
* :func:`brier_score` — squared error on the calibrated probability.
  Sanity-checks calibration.
* :func:`hit_rate_far` — operational §2.5 metrics at a fixed threshold.
* :func:`mean_lead_time_hours` — operational §2.5 lead time given
  per-sample valuation times and event times.

The functions use numpy at runtime; the imports are local so the
package can be imported without numpy installed.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any


def auc_pr(y_true: Any, y_prob: Any) -> float:
    """Area under the precision-recall curve."""
    from sklearn.metrics import average_precision_score

    return float(average_precision_score(y_true, y_prob))


def brier_score(y_true: Any, y_prob: Any) -> float:
    from sklearn.metrics import brier_score_loss

    return float(brier_score_loss(y_true, y_prob))


def hit_rate_far(y_true: Any, y_prob: Any, *, threshold: float) -> tuple[float, float]:
    """Operational hit-rate + false-alarm-rate at the given probability cutoff."""
    import numpy as np

    yt = np.asarray(y_true, dtype=int)
    yp = (np.asarray(y_prob, dtype=float) >= threshold).astype(int)
    tp = int(((yp == 1) & (yt == 1)).sum())
    fp = int(((yp == 1) & (yt == 0)).sum())
    fn = int(((yp == 0) & (yt == 1)).sum())
    hit_rate = tp / (tp + fn) if (tp + fn) else 0.0
    far = fp / (fp + tp) if (fp + tp) else 0.0
    return float(hit_rate), float(far)


def mean_lead_time_hours(
    valuation_times: Sequence[datetime],
    event_times: Sequence[datetime],
    *,
    hits: Sequence[bool],
) -> float:
    """Mean (event - valuation) for hit samples, in hours."""
    deltas: list[float] = []
    for vt, et, hit in zip(valuation_times, event_times, hits, strict=True):
        if not hit:
            continue
        delta = (et - vt).total_seconds() / 3600.0
        if delta > 0:
            deltas.append(delta)
    return sum(deltas) / len(deltas) if deltas else 0.0


def tss(y_true: Any, y_prob: Any, *, threshold: float) -> tuple[float, float, float]:
    """(TSS, sensitivity, specificity) at a probability cutoff.

    TSS = sensitivity + specificity - 1 — the skill score landslide
    literature prefers because, unlike accuracy, it is insensitive to
    the negative/positive imbalance of the dataset.
    """
    import numpy as np

    yt = np.asarray(y_true, dtype=int)
    yp = (np.asarray(y_prob, dtype=float) >= threshold).astype(int)
    tp = int(((yp == 1) & (yt == 1)).sum())
    fp = int(((yp == 1) & (yt == 0)).sum())
    fn = int(((yp == 0) & (yt == 1)).sum())
    tn = int(((yp == 0) & (yt == 0)).sum())
    sens = tp / (tp + fn) if (tp + fn) else 0.0
    spec = tn / (tn + fp) if (tn + fp) else 0.0
    return float(sens + spec - 1.0), float(sens), float(spec)


def threshold_sweep(
    y_true: Any,
    y_prob: Any,
    *,
    recall_targets: Sequence[float] = (0.5, 0.7, 0.9),
) -> list[dict[str, float]]:
    """Operating points at fixed recall targets (50/70/90% by default).

    For each target, picks the highest threshold whose recall meets it,
    then reports FAR / TSS / specificity there — "what does it cost to
    catch X% of the landslides with this scorer?".
    """
    import numpy as np

    yt = np.asarray(y_true, dtype=int)
    yp = np.asarray(y_prob, dtype=float)
    positives = yp[yt == 1]
    out: list[dict[str, float]] = []
    for target in recall_targets:
        if positives.size == 0:
            out.append({"recall_target": float(target), "threshold": 1.0})
            continue
        # The (1-target) quantile of positive scores is the highest
        # threshold that still classifies `target` of positives as hits.
        threshold = float(np.quantile(positives, 1.0 - target))
        hit, far = hit_rate_far(yt, yp, threshold=threshold)
        skill, sens, spec = tss(yt, yp, threshold=threshold)
        out.append(
            {
                "recall_target": float(target),
                "threshold": threshold,
                "hit_rate": hit,
                "far": far,
                "tss": skill,
                "sensitivity": sens,
                "specificity": spec,
            }
        )
    return out


def conformal_quantiles(
    y_true: Any,
    y_prob: Any,
    *,
    alphas: Sequence[float] = (0.2, 0.1, 0.05),
) -> dict[str, float]:
    """Split-conformal error quantiles on the calibration set.

    Nonconformity = |y - p_calibrated|. For each miscoverage ``alpha``
    the returned ``q`` guarantees (marginally) that
    ``[p - q, p + q]`` covers the outcome with probability ≥ 1 - alpha
    on exchangeable data. Reuses the isotonic-calibrated OOF
    predictions — no extra data split needed.
    """
    import numpy as np

    yt = np.asarray(y_true, dtype=float)
    yp = np.asarray(y_prob, dtype=float)
    scores = np.abs(yt - yp)
    n = scores.size
    out: dict[str, float] = {}
    for alpha in alphas:
        # Finite-sample corrected quantile rank (Vovk).
        rank = min(1.0, np.ceil((n + 1) * (1 - alpha)) / n)
        out[f"q{int((1 - alpha) * 100)}"] = float(np.quantile(scores, rank))
    return out


__all__ = [
    "auc_pr",
    "brier_score",
    "conformal_quantiles",
    "hit_rate_far",
    "mean_lead_time_hours",
    "threshold_sweep",
    "tss",
]
