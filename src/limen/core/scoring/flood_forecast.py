"""Dynamic, multi-source flood uplift (issue #8).

Pure function: combine forward-looking flood signals — pluvial (forecast rain),
fluvial (river-discharge ratio vs normal, Open-Meteo Flood API / GloFAS) and
coastal (sea surge, Open-Meteo Marine API) — into an additive uplift for the
engine's hydrology quota H, scaled by the ISPRA static hydraulic hazard. No
I/O. Returns 0.0 whenever the static hazard or every forecast signal is
missing, so a bundle without the flood feed scores byte-identical to V1.
"""

from __future__ import annotations

import math

from limen.core.scoring.regional_thresholds import FloodForecastBlock


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


def flood_forecast_bonus(
    *,
    rain_72h_mm: float | None,
    river_discharge_ratio: float | None,
    coastal_surge_norm: float | None,
    flood_hazard_norm: float | None,
    macroregion: str,
    cfg: FloodForecastBlock,
) -> float:
    """Additive uplift for H = ``hazard_uplift · hazard · max(signals)``.

    Signals (each 0 when its input is absent):
    * pluvial = sigmoid((rain − center)/steepness), per macroregion;
    * fluvial = sigmoid((discharge_ratio − center)/steepness);
    * coastal = clamp01(coastal_surge_norm).
    """
    if flood_hazard_norm is None or flood_hazard_norm <= 0.0:
        return 0.0
    mr = cfg.macroregions.get(macroregion) or cfg.macroregions["italy_default"]

    pluvial = _sigmoid((rain_72h_mm - mr.center_mm) / mr.steepness_mm) if rain_72h_mm else 0.0
    fluvial = (
        _sigmoid(
            (river_discharge_ratio - cfg.discharge_ratio_center) / cfg.discharge_ratio_steepness
        )
        if river_discharge_ratio
        else 0.0
    )
    coastal = 0.0
    if coastal_surge_norm is not None:
        coastal = min(1.0, max(0.0, coastal_surge_norm))

    signal = max(pluvial, fluvial, coastal)
    bonus = cfg.hazard_uplift * flood_hazard_norm * signal
    return bonus if bonus < 1.0 else 1.0
