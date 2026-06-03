"""Antecedent Precipitation Index (Kohler & Linsley 1951).

Two related computations:

1. :func:`api_kohler_linsley` — recursive ``API_t = k·API_{t-1} + P_t``
   over an hourly or daily series. Returns the final API value.
2. :func:`api_factor` — converts an API value into a 0..1 "wetness"
   factor through a logistic transform of the standardised anomaly
   against a per-cell, per-month baseline. The σ and the baseline
   fallback come from :class:`ApiBlock`.

Both functions are pure: no I/O, no time-of-day surprises.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

from limen.core.scoring.regional_thresholds import ApiBlock


def api_kohler_linsley(
    daily_precip_mm: Iterable[float],
    *,
    decay_k: float,
    initial: float = 0.0,
) -> float:
    """Run the recursive Kohler–Linsley API on a daily-precip iterable.

    Args:
        daily_precip_mm: Daily totals in chronological order.
        decay_k: Daily decay coefficient (``0 < k < 1``).
        initial: API at the start of the series (defaults to 0).

    Returns:
        API at the end of the series.
    """
    if not 0.0 < decay_k < 1.0:
        raise ValueError(f"decay_k must be in (0, 1), got {decay_k}")
    api = float(initial)
    for p in daily_precip_mm:
        if p < 0.0:
            raise ValueError(f"daily_precip_mm must be >= 0, got {p}")
        api = decay_k * api + float(p)
    return api


def _sigmoid(z: float) -> float:
    if z >= 0:
        ez = math.exp(-z)
        return 1.0 / (1.0 + ez)
    ez = math.exp(z)
    return ez / (1.0 + ez)


def api_factor(
    api_30_mm: float | None,
    *,
    api: ApiBlock,
    baseline_mm: float | None = None,
) -> float:
    """Convert API_30 into a 0..1 wetness factor.

    Defaults to **0.5** (the sigmoid centre, "neutral") when no API
    information is available, so a missing input does not bias the
    score upward or downward.
    """
    if api_30_mm is None:
        return 0.5
    baseline = baseline_mm if baseline_mm is not None else api.baseline.fallback_mm
    sigma = api.sigmoid_sigma_mm
    if sigma <= 0:
        raise ValueError(f"sigmoid_sigma_mm must be > 0, got {sigma}")
    z = (api_30_mm - baseline) / sigma
    return _sigmoid(z)
