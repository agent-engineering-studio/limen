"""Drift detection primitives.

Three signals (project doc §3.15):

* :func:`population_stability_index` — feature drift between the
  training distribution and a recent live distribution. Returns the
  classic PSI bucketed against deciles of the reference distribution.
* :func:`ks_distance` — non-parametric Kolmogorov-Smirnov statistic
  on the two empirical distributions.
* :func:`prediction_drift` — absolute change in mean predicted
  probability between two windows.

Each function takes plain ``Sequence[float]`` inputs and returns a
plain float — no model objects, no DB. Compose them in :mod:`trigger`.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DriftReport:
    """Headline drift values + booleans against configured thresholds."""

    psi: float
    ks: float
    pred_drift: float
    psi_alert: bool
    ks_alert: bool
    pred_alert: bool

    @property
    def any_alert(self) -> bool:
        return self.psi_alert or self.ks_alert or self.pred_alert


def _safe_log(x: float) -> float:
    return math.log(max(x, 1e-9))


def population_stability_index(
    reference: Sequence[float],
    candidate: Sequence[float],
    *,
    n_buckets: int = 10,
) -> float:
    """PSI between two univariate distributions.

    Buckets are quantile-based on the reference. Empty buckets get a
    small floor to keep the log finite.
    """
    if not reference or not candidate:
        return 0.0

    sorted_ref = sorted(reference)
    bucket_edges = [
        sorted_ref[min(int(i / n_buckets * (len(sorted_ref) - 1)), len(sorted_ref) - 1)]
        for i in range(n_buckets + 1)
    ]
    # Force the last edge to be the max to capture the tail.
    bucket_edges[-1] = sorted_ref[-1]

    def _hist(values: Sequence[float]) -> list[float]:
        counts = [0] * n_buckets
        for v in values:
            for i in range(n_buckets):
                lo, hi = bucket_edges[i], bucket_edges[i + 1]
                if (v >= lo and v < hi) or (i == n_buckets - 1 and v == hi):
                    counts[i] += 1
                    break
        total = float(sum(counts)) or 1.0
        return [c / total for c in counts]

    ref_hist = _hist(reference)
    cand_hist = _hist(candidate)
    psi = 0.0
    for r, c in zip(ref_hist, cand_hist, strict=True):
        r_safe = max(r, 1e-6)
        c_safe = max(c, 1e-6)
        psi += (c_safe - r_safe) * (_safe_log(c_safe) - _safe_log(r_safe))
    # Defensive: PSI is sometimes negative due to floating-point noise.
    return float(max(psi, 0.0))


def ks_distance(reference: Sequence[float], candidate: Sequence[float]) -> float:
    """Two-sample Kolmogorov-Smirnov statistic ∈ [0, 1].

    Computes ``max_x |F_a(x) - F_b(x)|`` on the empirical CDFs. Ties
    between the two samples advance both pointers — important so the
    statistic is exactly zero on identical inputs.
    """
    if not reference or not candidate:
        return 0.0
    a = sorted(reference)
    b = sorted(candidate)
    n_a = float(len(a))
    n_b = float(len(b))
    i = j = 0
    ks = 0.0
    while i < len(a) and j < len(b):
        if a[i] < b[j]:
            i += 1
        elif a[i] > b[j]:
            j += 1
        else:
            # Equal values — advance both so identical samples → KS = 0.
            i += 1
            j += 1
        diff = abs(i / n_a - j / n_b)
        if diff > ks:
            ks = diff
    # Finish remaining tail.
    while i < len(a):
        i += 1
        diff = abs(i / n_a - j / n_b)
        if diff > ks:
            ks = diff
    while j < len(b):
        j += 1
        diff = abs(i / n_a - j / n_b)
        if diff > ks:
            ks = diff
    return float(ks)


def prediction_drift(reference_probs: Sequence[float], candidate_probs: Sequence[float]) -> float:
    """Absolute change in mean predicted probability."""
    if not reference_probs or not candidate_probs:
        return 0.0
    return float(
        abs(
            sum(candidate_probs) / len(candidate_probs)
            - sum(reference_probs) / len(reference_probs)
        )
    )


def make_report(
    *,
    reference: Sequence[float],
    candidate: Sequence[float],
    reference_probs: Sequence[float],
    candidate_probs: Sequence[float],
    psi_alert: float,
    ks_alert: float,
    pred_alert: float,
) -> DriftReport:
    psi = population_stability_index(reference, candidate)
    ks = ks_distance(reference, candidate)
    pd = prediction_drift(reference_probs, candidate_probs)
    return DriftReport(
        psi=psi,
        ks=ks,
        pred_drift=pd,
        psi_alert=psi >= psi_alert,
        ks_alert=ks >= ks_alert,
        pred_alert=pd >= pred_alert,
    )


__all__: list[Any] = [
    "DriftReport",
    "ks_distance",
    "make_report",
    "population_stability_index",
    "prediction_drift",
]
