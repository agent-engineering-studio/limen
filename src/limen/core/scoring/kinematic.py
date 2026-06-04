"""V1.5 K component — pure functions over :class:`SensorFeatures`.

Used by :class:`MultiFactorScoringEngine` when a cell carries an in-situ
``SensorFeatures`` aggregate. With no sensor coverage, K stays zero and
the engine produces the same score as V1.

Math (per project doc §2.9):

* ``velocity_score = sigmoid( (v - v_thr) / sigma_v )`` — monotone in v,
  smooth around the YAML's ``v_threshold_mmd``.
* ``acceleration_score`` — sigmoid on the acceleration alarm threshold;
  exceeding the alarm forces ``hard_escalation=True`` and an upper bound
  on K so the alert dispatcher fires.
* ``K`` blends the two with a Fukuzono inverse-velocity *boost* when the
  inverse-velocity is below the configured alarm (a precursor to
  imminent failure).
"""

from __future__ import annotations

import math

from limen.core.models.risk import KinematicBreakdown
from limen.core.models.sensor import SensorFeatures
from limen.core.scoring.regional_thresholds import KinematicBlock


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


def compute_kinematic(
    features: SensorFeatures | None,
    *,
    kinematic: KinematicBlock | None,
) -> tuple[float, KinematicBreakdown]:
    """Return ``(K, KinematicBreakdown)`` for the given features.

    Inactive (returns 0 + a zero breakdown) when either the YAML block is
    absent (V1 config) or the features have no kinematic signal.
    """
    if kinematic is None or features is None or not features.has_kinematic_signal:
        return 0.0, KinematicBreakdown()

    velocity = features.velocity_mmd
    acceleration = features.acceleration_mmd2
    inv_v = features.inverse_velocity

    velocity_score = 0.0
    if velocity is not None:
        z = (velocity - kinematic.v_threshold_mmd) / kinematic.sigma_v
        velocity_score = _sigmoid(z)

    hard_escalation = False
    acceleration_score = 0.0
    if acceleration is not None:
        # Centre the sigmoid on the alarm threshold; the steepness is the
        # alarm itself so that one alarm-worth of acceleration shifts the
        # sigmoid from 0.5 → ~0.73.
        z = (acceleration - kinematic.acceleration_alarm_mmd2) / kinematic.acceleration_alarm_mmd2
        acceleration_score = _sigmoid(z)
        if acceleration >= kinematic.acceleration_alarm_mmd2:
            hard_escalation = True

    # Inverse-velocity boost: if 1/v ≤ alarm, the cell is in Fukuzono's
    # imminent-failure regime — raise K to ≥ 0.8 and force hard escalation.
    boost = 0.0
    if inv_v is not None and inv_v <= kinematic.inverse_velocity_alarm:
        boost = 0.8
        hard_escalation = True

    base = max(velocity_score, acceleration_score)
    k_value = _clamp01(max(base, boost))
    if hard_escalation:
        # Guarantee K reaches the high band even when individual scores
        # haven't quite saturated; the alert dispatcher reads ``hard_escalation``
        # directly, but persisted K should reflect the regime.
        k_value = max(k_value, 0.8)

    return k_value, KinematicBreakdown(
        velocity_mmd=velocity,
        acceleration_mmd2=acceleration,
        inverse_velocity=inv_v,
        velocity_score=_clamp01(velocity_score),
        acceleration_score=_clamp01(acceleration_score),
        hard_escalation=hard_escalation,
    )


__all__ = ["compute_kinematic"]
