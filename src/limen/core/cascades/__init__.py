"""Regole di cascata fra pericoli (#58): configurazione e funzioni pure."""

from limen.core.cascades.config import CascadeRules, load_cascades
from limen.core.cascades.rules import (
    JointCell,
    joint_rain_cells,
    post_fire_flood_multiplier,
)

__all__ = [
    "CascadeRules",
    "JointCell",
    "joint_rain_cells",
    "load_cascades",
    "post_fire_flood_multiplier",
]
