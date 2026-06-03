"""Post-fire amplification window (§2.4).

A burnt slope is hydrologically distinct for ~2 years after a fire:
infiltration drops, runoff and shallow-instability risk increases.
We model the amplification factor as a Gaussian bell centred at
``peak_months`` and zero outside ``[0, window_months_max]``:

    F(m) = exp(−((m − peak_months)² / curve_denominator))    if 0 ≤ m ≤ window_max
         = 0                                                 otherwise

Pure function of ``months_since_fire`` and :class:`PostFireBlock`.
"""

from __future__ import annotations

import math

from limen.core.scoring.regional_thresholds import PostFireBlock


def post_fire_factor(
    months_since_fire: float | None,
    *,
    post_fire: PostFireBlock,
) -> float:
    """Return ``F`` in [0, 1]. ``None`` (no recent fire) → 0."""
    if months_since_fire is None:
        return 0.0
    if months_since_fire < 0 or months_since_fire > post_fire.window_months_max:
        return 0.0
    if post_fire.curve_denominator <= 0:
        raise ValueError(
            f"post_fire.curve_denominator must be > 0, got {post_fire.curve_denominator}"
        )
    return math.exp(
        -((months_since_fire - post_fire.peak_months) ** 2) / post_fire.curve_denominator
    )
