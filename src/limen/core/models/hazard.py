"""The hazard dimension.

Limen scores one kind of danger today (landslide) and is being opened up to
flood and wildfire. Every persisted risk statement, every dedup ledger and
every scoring engine is keyed on this enum, so it lives on its own with no
imports from the rest of the domain: the SQL enum ``hazard_type``, the
scoring registry and the DTOs all have to agree on it.

``DEFAULT_HAZARD`` is the single place the fallback is written down. Repos and
API surfaces default to it so callers that predate the hazard dimension keep
working unchanged.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class HazardType(StrEnum):
    """Hazards Limen can score. Values match the SQL ``hazard_type`` enum."""

    LANDSLIDE = "landslide"
    FLOOD = "flood"
    WILDFIRE = "wildfire"


DEFAULT_HAZARD: Final = HazardType.LANDSLIDE

__all__ = ["DEFAULT_HAZARD", "HazardType"]
