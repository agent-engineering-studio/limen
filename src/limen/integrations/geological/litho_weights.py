"""Lithology → susceptibility weight (0…1).

Maps the broad ISPRA / CARG lithology classes to a normalised
landslide-susceptibility weight, lifted from the §2.3 table in the
project doc. Unmapped strings get the neutral value 0.5 so the row
still imports.

The list is deliberately small + opinionated: callers can override
per-AOI via ``regional_thresholds.yaml`` if a regional study suggests
a different weight, but the default keeps demos sensible without YAML
edits.
"""

from __future__ import annotations

# Keys are lower-cased, stripped, and whitespace-collapsed. The matcher
# in :func:`normalise_litho` does a substring match so common ISPRA
# multi-word labels (e.g. "argille marnose") map to the right family.
LITHO_WEIGHTS: dict[str, float] = {
    # High susceptibility — clays + flysch + chaotic complexes.
    "argille": 0.85,
    "flysch": 0.80,
    "complesso caotico": 0.85,
    "scisti": 0.75,
    # Medium-high — sands + silts + tuffs.
    "sabbie": 0.65,
    "limi": 0.65,
    "tufi": 0.60,
    "marne": 0.70,
    # Medium — alluvial deposits + conglomerates.
    "alluvioni": 0.55,
    "conglomerati": 0.50,
    # Low — limestone + dolomites + crystalline.
    "calcari": 0.30,
    "dolomie": 0.30,
    "graniti": 0.20,
    "gneiss": 0.25,
    "vulcaniti": 0.40,
}

DEFAULT_LITHO_WEIGHT = 0.5
"""Returned for unmapped strings — neutral, neither high nor low."""


def normalise_litho(raw: str | None) -> tuple[str, float]:
    """Map a raw lithology label to ``(canonical_key, weight)``.

    Returns ``("unknown", DEFAULT_LITHO_WEIGHT)`` when no key matches.
    """
    if not raw:
        return "unknown", DEFAULT_LITHO_WEIGHT
    cleaned = " ".join(str(raw).strip().lower().split())
    for key, weight in LITHO_WEIGHTS.items():
        if key in cleaned:
            return key, weight
    return "unknown", DEFAULT_LITHO_WEIGHT


__all__ = ["DEFAULT_LITHO_WEIGHT", "LITHO_WEIGHTS", "normalise_litho"]
