"""Lithology → susceptibility weight (0…1).

The table lives in ``hazards/landslide.yaml`` (``static.lithology``): the
weight is a landslide calibration, not a property of the map. Unmapped
labels get the YAML ``default`` so the row still imports.
"""

from __future__ import annotations

from limen.core.scoring.regional_thresholds import LithologyWeights, load_regional_thresholds


def litho_weight_for(raw: str | None, weights: LithologyWeights | None = None) -> float:
    """The susceptibility weight of a raw lithology label."""
    table = weights if weights is not None else load_regional_thresholds().static.lithology
    return table.weight_for(raw)


__all__ = ["litho_weight_for"]
