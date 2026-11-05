"""Caine I/D rainfall threshold (Caine 1980; Brunetti et al. 2010).

Power law for the empirical rainfall **intensity–duration** triggering
threshold of shallow landslides:

    I_threshold(D) = α · D^(−β)            (I in mm/h, D in hours)

The Limen engine compares the *event* intensity ``I_event`` against
``I_threshold`` for the *event* duration ``D_event``:

    caine_excess = max(0, log(I_event) − log(I_threshold(D_event, region)))

Event detection from an hourly rainfall series follows a Melillo et al.
2018-inspired rule:

* split the series wherever there is a contiguous run of "dry" hours of
  length ``no_rain_break_hours`` or longer;
* keep events whose cumulated precipitation is at least ``min_event_mm``;
* for each event, report ``(I_event = total_mm / duration_h, D_event)``.

The power law and the event reconstruction come from the
``rainfall-thresholds`` package (extracted from Limen, Apache-2.0); the
parameters still come from :class:`RegionalThresholds.caine` — no
hard-coded constants here, and none taken from the package.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta

from rainfall_thresholds import PowerLawThreshold, RainfallEvent, latest_event
from rainfall_thresholds import reconstruct_events as _reconstruct

from limen.core.models.risk import RainfallSample, RainfallSeries
from limen.core.scoring.regional_thresholds import (
    CaineBlock,
    CaineMacroregion,
)


def _resolve_region(caine: CaineBlock, macroregion: str) -> CaineMacroregion:
    region = caine.macroregions.get(macroregion)
    if region is None:
        return caine.macroregions["italy_default"]
    return region


def _threshold(caine: CaineBlock, macroregion: str, alpha_factor: float = 1.0) -> PowerLawThreshold:
    region = _resolve_region(caine, macroregion)
    return PowerLawThreshold(alpha=region.alpha * alpha_factor, beta=region.beta)


def threshold_intensity_mm_h(
    duration_hours: float,
    *,
    caine: CaineBlock,
    macroregion: str = "italy_default",
) -> float:
    """Return ``I_threshold(D) = α · D^(−β)`` in mm/h."""
    return _threshold(caine, macroregion).intensity(duration_hours)


def reconstruct_events(
    samples: Iterable[RainfallSample],
    *,
    no_rain_break_hours: int,
    min_event_mm: float,
) -> list[RainfallEvent]:
    """Split an hourly rainfall series into discrete events."""
    return _reconstruct(
        ((s.timestamp, s.precipitation_mm) for s in samples),
        no_rain_break_hours=no_rain_break_hours,
        min_event_mm=min_event_mm,
    )


def caine_excess(
    event: RainfallEvent | None,
    *,
    caine: CaineBlock,
    macroregion: str = "italy_default",
    alpha_factor: float = 1.0,
) -> float:
    """Compute ``max(0, log10(I_event) − log10(I_threshold(D)))``.

    Returns 0 when no event is provided or when the event sits below
    the threshold. Using ``log10`` keeps the magnitude human-friendly
    on the order of "fraction of a decade above the threshold".
    ``alpha_factor`` scales α (a post-earthquake threshold is lower, #441).
    """
    if event is None:
        return 0.0
    excess = _threshold(caine, macroregion, alpha_factor).exceedance(
        event.intensity_mm_h, event.duration_hours
    )
    # -inf (a dry event) goes to zero; +inf from a corrupt series stays.
    return excess if excess > 0.0 else 0.0


def compute_caine(
    rainfall: RainfallSeries,
    *,
    caine: CaineBlock,
    macroregion: str = "italy_default",
    as_of_window: timedelta | None = None,
    alpha_factor: float = 1.0,
) -> tuple[float, RainfallEvent | None]:
    """End-to-end Caine computation for a rainfall series.

    Returns ``(caine_excess, latest_event)``. ``as_of_window``, when set,
    restricts event reconstruction to samples within that trailing
    window relative to the latest sample — useful at runtime where the
    bundle assembler may hand the engine a long series.
    """
    samples: list[RainfallSample] = list(rainfall.samples)
    if as_of_window is not None and samples:
        latest_ts = samples[-1].timestamp
        cutoff = latest_ts - as_of_window
        samples = [s for s in samples if s.timestamp >= cutoff]

    events = reconstruct_events(
        samples,
        no_rain_break_hours=caine.event_reconstruction.no_rain_break_hours,
        min_event_mm=caine.event_reconstruction.min_event_mm,
    )
    event = latest_event(events)
    excess = caine_excess(event, caine=caine, macroregion=macroregion, alpha_factor=alpha_factor)
    return excess, event


__all__ = [
    "RainfallEvent",
    "caine_excess",
    "compute_caine",
    "latest_event",
    "reconstruct_events",
    "threshold_intensity_mm_h",
]
