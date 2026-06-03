"""Local PGA with exponential time decay (§2.4).

For every seismic event ``i`` in the lookback window with
``M ≥ min_magnitude``:

    pga_decayed_i = PGA_event_i · exp(−Δt_i / τ)

``pga_local`` is then the max over all events. The seismic E-component
is the sigmoid:

    E = sigmoid((pga_local − pga_threshold) / pga_scale)

falling to 0 when no event exceeds the lookback window or magnitude
threshold. Units of g (gravitational acceleration) throughout.

Local PGA estimation per event is *out of scope* for this prompt — it
comes from INGV ShakeMap when available (Phase 2) or, in a future
prompt, from a GMPE attenuation model. The bundle assembler hands the
engine the per-event PGA, the engine only does the decay + sigmoid.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import datetime

from limen.core.models.risk import SeismicHistoryEvent
from limen.core.scoring.regional_thresholds import SeismicBlock


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


def pga_local(
    events: Iterable[SeismicHistoryEvent],
    *,
    as_of: datetime,
    seismic: SeismicBlock,
) -> float:
    """Return the decayed local PGA in g (0 if no qualifying event)."""
    tau_days = seismic.tau_days
    if tau_days <= 0:
        raise ValueError(f"tau_days must be > 0, got {tau_days}")

    max_pga = 0.0
    for ev in events:
        if ev.magnitude < seismic.min_magnitude:
            continue
        dt_days = (as_of - ev.origin_time).total_seconds() / 86_400.0
        if dt_days < 0 or dt_days > seismic.lookback_days:
            continue
        decayed = ev.pga_g * math.exp(-dt_days / tau_days)
        if decayed > max_pga:
            max_pga = decayed
    return max_pga


def seismic_factor(
    pga: float,
    *,
    seismic: SeismicBlock,
) -> float:
    """Sigmoid-transform a local PGA (in g) into a 0..1 factor.

    Returns 0 below the threshold so quiet conditions do not contribute
    a baseline seismic load.
    """
    if pga <= 0:
        return 0.0
    z = (pga - seismic.pga_threshold_g) / seismic.pga_scale_g
    return _sigmoid(z)


def compute_seismic(
    events: Iterable[SeismicHistoryEvent],
    *,
    as_of: datetime,
    seismic: SeismicBlock,
) -> tuple[float, float]:
    """Convenience: returns ``(pga_local_g, seismic_factor)``."""
    pga = pga_local(events, as_of=as_of, seismic=seismic)
    return pga, seismic_factor(pga, seismic=seismic)
