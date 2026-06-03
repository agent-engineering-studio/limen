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

All parameters come from :class:`RegionalThresholds.caine` — no
hard-coded constants in this module.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta

from limen.core.models.risk import RainfallSample, RainfallSeries
from limen.core.scoring.regional_thresholds import (
    CaineBlock,
    CaineMacroregion,
)


@dataclass(frozen=True, slots=True)
class RainfallEvent:
    """One reconstructed rainfall event."""

    start: int
    end: int
    duration_hours: float
    total_mm: float

    @property
    def intensity_mm_h(self) -> float:
        return self.total_mm / self.duration_hours if self.duration_hours > 0 else 0.0


def _resolve_region(caine: CaineBlock, macroregion: str) -> CaineMacroregion:
    region = caine.macroregions.get(macroregion)
    if region is None:
        return caine.macroregions["italy_default"]
    return region


def threshold_intensity_mm_h(
    duration_hours: float,
    *,
    caine: CaineBlock,
    macroregion: str = "italy_default",
) -> float:
    """Return ``I_threshold(D) = α · D^(−β)`` in mm/h."""
    if duration_hours <= 0:
        raise ValueError(f"duration_hours must be > 0, got {duration_hours}")
    region = _resolve_region(caine, macroregion)
    return float(region.alpha * (duration_hours ** (-region.beta)))


def reconstruct_events(
    samples: Iterable[RainfallSample],
    *,
    no_rain_break_hours: int,
    min_event_mm: float,
) -> list[RainfallEvent]:
    """Split an hourly rainfall series into discrete events."""
    series = sorted(samples, key=lambda s: s.timestamp)
    if not series:
        return []

    events: list[RainfallEvent] = []
    current_start: int | None = None
    current_total: float = 0.0
    dry_run: int = 0
    last_wet_idx: int | None = None

    def _close() -> None:
        nonlocal current_start, current_total, last_wet_idx
        if current_start is None or last_wet_idx is None:
            current_start = None
            current_total = 0.0
            last_wet_idx = None
            return
        start_ts = series[current_start].timestamp
        end_ts = series[last_wet_idx].timestamp
        duration_h = max(1.0, (end_ts - start_ts).total_seconds() / 3600.0 + 1.0)
        if current_total >= min_event_mm:
            events.append(
                RainfallEvent(
                    start=current_start,
                    end=last_wet_idx,
                    duration_hours=duration_h,
                    total_mm=current_total,
                )
            )
        current_start = None
        current_total = 0.0
        last_wet_idx = None

    for i, sample in enumerate(series):
        if sample.precipitation_mm > 0.0:
            if current_start is None:
                current_start = i
            current_total += sample.precipitation_mm
            last_wet_idx = i
            dry_run = 0
        else:
            dry_run += 1
            if dry_run >= no_rain_break_hours and current_start is not None:
                _close()

    if current_start is not None:
        _close()

    return events


def latest_event(events: list[RainfallEvent]) -> RainfallEvent | None:
    """Return the most recent (by end index) event, or ``None``."""
    return max(events, key=lambda e: e.end) if events else None


def caine_excess(
    event: RainfallEvent | None,
    *,
    caine: CaineBlock,
    macroregion: str = "italy_default",
) -> float:
    """Compute ``max(0, log10(I_event) − log10(I_threshold(D)))``.

    Returns 0 when no event is provided or when the event sits below
    the threshold. Using ``log10`` keeps the magnitude human-friendly
    on the order of "fraction of a decade above the threshold".
    """
    if event is None or event.duration_hours <= 0 or event.intensity_mm_h <= 0:
        return 0.0
    i_thr = threshold_intensity_mm_h(event.duration_hours, caine=caine, macroregion=macroregion)
    if i_thr <= 0:
        return 0.0
    return max(0.0, math.log10(event.intensity_mm_h) - math.log10(i_thr))


def compute_caine(
    rainfall: RainfallSeries,
    *,
    caine: CaineBlock,
    macroregion: str = "italy_default",
    as_of_window: timedelta | None = None,
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
    excess = caine_excess(event, caine=caine, macroregion=macroregion)
    return excess, event
