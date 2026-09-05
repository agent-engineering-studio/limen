"""Pure flood triggers: how much water, and from where (#63).

Two independent ways for a cell to end up under water, each reduced to a
number in [0, 1]:

* **pluvial** — rain falling faster than the ground and the drains can take
  it. An intensity-duration threshold, the same shape as the Caine landslide
  threshold and with its own numbers, damped by how dry the soil was and
  amplified by how sealed the surface is.
* **fluvial** — a river arriving from somewhere else entirely. Forecast peak
  discharge against the recent normal.

Both are pure functions of their arguments plus the hazard's configuration.
The distinction matters operationally: the same cell can be safe from one and
not the other, and the two are mitigated by different things.
"""

from __future__ import annotations

from limen.core.scoring.regional_thresholds import (
    FluvialBlock,
    ImperviousnessBlock,
    PluvialBlock,
)

__all__ = ["fluvial_trigger", "pluvial_trigger"]


def _ramp(value: float, lo: float, hi: float) -> float:
    """Linear 0→1 between ``lo`` and ``hi``, clamped outside."""
    if value <= lo:
        return 0.0
    if value >= hi:
        return 1.0
    return (value - lo) / (hi - lo)


def pluvial_trigger(
    rain_mm: float | None,
    *,
    soil_moisture: float | None,
    imperviousness: float | None,
    pluvial: PluvialBlock,
    imperviousness_cfg: ImperviousnessBlock,
) -> float:
    """Local flooding from rain, in [0, 1]. ``None`` rain ⇒ 0.

    Soil moisture damps and imperviousness amplifies, in that order: sealed
    ground is sealed whatever the soil under it is doing, so the multiplier
    applies after the damping rather than fighting with it.

    Unknown soil moisture is treated as *neither* dry nor saturated -- the
    trigger passes through undamped. Guessing dry would suppress a real
    warning; guessing wet would invent one.
    """
    if rain_mm is None:
        return 0.0

    base = _ramp(rain_mm, pluvial.threshold_mm, pluvial.saturation_mm)
    if base <= 0.0:
        return 0.0

    if soil_moisture is not None:
        # Dry ground absorbs the first rain; saturated ground sheds all of it.
        wetness = min(soil_moisture / pluvial.wet_soil, 1.0) if pluvial.wet_soil > 0 else 1.0
        damping = pluvial.dry_soil_factor + (1.0 - pluvial.dry_soil_factor) * wetness
        base *= damping

    if imperviousness is not None:
        multiplier = 1.0 + (imperviousness_cfg.max_multiplier - 1.0) * imperviousness
        base *= multiplier

    return min(base, 1.0)


def fluvial_trigger(discharge_ratio: float | None, *, fluvial: FluvialBlock) -> float:
    """River flooding, in [0, 1]. ``None`` ratio ⇒ 0.

    Zero for an absent signal, not for a *low* one: a cell with no river
    nearby has no fluvial risk, and Open-Meteo returns nothing rather than a
    ratio for such a point. The two cases coincide in the answer, so no
    special handling is needed -- but they are different facts, which is why
    the breakdown carries the raw ratio.
    """
    return _ramp(discharge_ratio or 0.0, fluvial.normal_ratio, fluvial.saturation_ratio)
