"""Canadian Fire Weather Index chain — Van Wagner (1987), pure functions.

Six numbers computed from four daily readings taken at local noon
(temperature, relative humidity, 10 m wind, rain over the previous 24 h):

    FFMC  fine fuel moisture, memory ~2/3 day   ┐
    DMC   duff moisture, memory ~12 days        ├─ three moisture codes
    DC    drought code, memory ~52 days         ┘
    ISI   FFMC × wind        → rate of spread
    BUI   DMC + DC           → available fuel
    FWI   ISI + BUI          → the index EFFIS publishes for Europe

The three moisture codes are **recursive**: today's value is a function of
yesterday's. That is the whole reason this module has a state DTO and the
caller has a table -- a code started from its standard initial value needs
weeks of spin-up before it means anything, so the state has to survive
process restarts.

Everything here is a pure function of its arguments plus a
:class:`FwiParams`: no I/O, no clock, no configuration lookup. The numeric
constants below are Van Wagner's, transcribed from the equations rather than
tuned, so they are *not* in the YAML -- what belongs there is anything a
deployment may legitimately choose (initial codes, day-length tables,
normalisation), and that is what :class:`FwiParams` carries.

Reference: Van Wagner, C.E. (1987), *Development and structure of the
Canadian Forest Fire Weather Index System*, Forestry Technical Report 35.
Equation numbers in the comments are that report's.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = [
    "FwiOutputs",
    "FwiParams",
    "FwiState",
    "advance",
    "buildup_index",
    "drought_code",
    "duff_moisture_code",
    "fine_fuel_moisture_code",
    "fire_weather_index",
    "initial_spread_index",
]


@dataclass(frozen=True, slots=True)
class FwiState:
    """The three recursive codes carried from one day to the next."""

    ffmc: float
    dmc: float
    dc: float


@dataclass(frozen=True, slots=True)
class FwiOutputs:
    """A day's full chain: the new state plus the three derived indices."""

    state: FwiState
    isi: float
    bui: float
    fwi: float


@dataclass(frozen=True, slots=True)
class FwiParams:
    """What a deployment may choose, as opposed to what Van Wagner fixed.

    ``day_length_dmc`` and ``day_length_dc`` are the 12 monthly factors
    (January first) for the latitude band in use. Van Wagner tabulates them
    for 46°N, which is central Europe; Italy spans 36°N-47°N, so the
    published table is the right default and a deployment further from it
    can override without touching code.
    """

    ffmc_start: float
    dmc_start: float
    dc_start: float
    day_length_dmc: tuple[float, ...]
    day_length_dc: tuple[float, ...]

    def __post_init__(self) -> None:
        for name, table in (
            ("day_length_dmc", self.day_length_dmc),
            ("day_length_dc", self.day_length_dc),
        ):
            if len(table) != 12:
                raise ValueError(f"{name} must have 12 monthly entries, got {len(table)}")

    @property
    def initial_state(self) -> FwiState:
        return FwiState(ffmc=self.ffmc_start, dmc=self.dmc_start, dc=self.dc_start)


def _ffmc_to_moisture(ffmc: float) -> float:
    """Eq. 1 inverted: the FFMC scale back to % moisture content."""
    return 147.2 * (101.0 - ffmc) / (59.5 + ffmc)


def fine_fuel_moisture_code(
    previous: float,
    *,
    temperature_c: float,
    relative_humidity_pct: float,
    wind_speed_kmh: float,
    rain_24h_mm: float,
) -> float:
    """Eqs. 1-10. Fine fuel moisture on the 0-101 FFMC scale."""
    h = min(max(relative_humidity_pct, 0.0), 100.0)
    w = max(wind_speed_kmh, 0.0)
    mo = _ffmc_to_moisture(previous)

    if rain_24h_mm > 0.5:  # Eq. 2 — the 0.5 mm is canopy interception.
        rf = rain_24h_mm - 0.5
        absorbed = 42.5 * rf * math.exp(-100.0 / (251.0 - mo)) * (1.0 - math.exp(-6.93 / rf))
        # Eq. 3a. Both the test and the correction read the moisture *before*
        # the rain was added: above 150 % the fuel is already saturated, so
        # the extra water runs off rather than being absorbed. Testing the
        # post-rain value instead would apply the correction to fuels that
        # were dry at dawn, overstating their wetting.
        mo = mo + absorbed + (0.0015 * (mo - 150.0) ** 2 * math.sqrt(rf) if mo > 150.0 else 0.0)
        mo = min(mo, 250.0)

    # Eq. 4 / 5 — equilibrium moisture content for drying and for wetting.
    ed = (
        0.942 * h**0.679
        + 11.0 * math.exp((h - 100.0) / 10.0)
        + 0.18 * (21.1 - temperature_c) * (1.0 - math.exp(-0.115 * h))
    )
    if mo > ed:
        # Eq. 6 / 7 — log drying rate, then the day's drying.
        ko = 0.424 * (1.0 - (h / 100.0) ** 1.7) + 0.0694 * math.sqrt(w) * (1.0 - (h / 100.0) ** 8)
        kd = ko * 0.581 * math.exp(0.0365 * temperature_c)
        m = ed + (mo - ed) * 10.0**-kd
    else:
        ew = (
            0.618 * h**0.753
            + 10.0 * math.exp((h - 100.0) / 10.0)
            + 0.18 * (21.1 - temperature_c) * (1.0 - math.exp(-0.115 * h))
        )
        if mo < ew:
            # Eq. 8 / 9 — wetting, the mirror of the drying rate.
            kl = 0.424 * (1.0 - ((100.0 - h) / 100.0) ** 1.7) + 0.0694 * math.sqrt(w) * (
                1.0 - ((100.0 - h) / 100.0) ** 8
            )
            kw = kl * 0.581 * math.exp(0.0365 * temperature_c)
            m = ew - (ew - mo) * 10.0**-kw
        else:
            # Between the two equilibria nothing moves: this is the flat
            # hysteresis band, not a missing branch.
            m = mo

    ffmc = 59.5 * (250.0 - m) / (147.2 + m)  # Eq. 10
    # float(): `x ** y` on two floats is Any to mypy (the result may be complex).
    return float(min(max(ffmc, 0.0), 101.0))


def duff_moisture_code(
    previous: float,
    *,
    temperature_c: float,
    relative_humidity_pct: float,
    rain_24h_mm: float,
    day_length: float,
) -> float:
    """Eqs. 11-17. Moisture of loosely compacted organic layers."""
    h = min(max(relative_humidity_pct, 0.0), 100.0)
    # Eq. 16 — below -1.1 °C drying stops; the clamp *is* the equation.
    t = max(temperature_c, -1.1)
    rk = 1.894 * (t + 1.1) * (100.0 - h) * day_length * 1e-4

    if rain_24h_mm <= 1.5:  # Eq. 11 — below this the duff layer stays dry.
        return max(previous + rk, 0.0)

    re = 0.92 * rain_24h_mm - 1.27  # Eq. 11
    mo = 20.0 + math.exp(5.6348 - previous / 43.43)  # Eq. 12
    if previous <= 33.0:  # Eq. 13 a/b/c — slope of the wetting curve.
        b = 100.0 / (0.5 + 0.3 * previous)
    elif previous <= 65.0:
        b = 14.0 - 1.3 * math.log(previous)
    else:
        b = 6.2 * math.log(previous) - 17.2
    mr = mo + 1000.0 * re / (48.77 + b * re)  # Eq. 14
    pr = 244.72 - 43.43 * math.log(mr - 20.0)  # Eq. 15
    return max(max(pr, 0.0) + rk, 0.0)


def drought_code(
    previous: float,
    *,
    temperature_c: float,
    rain_24h_mm: float,
    day_length: float,
) -> float:
    """Eqs. 18-23. Deep, compact organic layers — the seasonal drought memory."""
    t = max(temperature_c, -2.8)  # Eq. 22
    pe = max((0.36 * (t + 2.8) + day_length) / 2.0, 0.0)  # Eq. 22

    if rain_24h_mm <= 2.8:  # Eq. 18
        return max(previous + pe, 0.0)

    rd = 0.83 * rain_24h_mm - 1.27  # Eq. 18
    qo = 800.0 * math.exp(-previous / 400.0)  # Eq. 19
    qr = qo + 3.937 * rd  # Eq. 20
    dr = max(400.0 * math.log(800.0 / qr), 0.0)  # Eq. 21
    return max(dr + pe, 0.0)


def initial_spread_index(ffmc: float, *, wind_speed_kmh: float) -> float:
    """Eqs. 24-26. Expected rate of spread — where wind enters the chain."""
    m = _ffmc_to_moisture(ffmc)
    f_wind = math.exp(0.05039 * max(wind_speed_kmh, 0.0))  # Eq. 24
    f_fine = 91.9 * math.exp(-0.1386 * m) * (1.0 + m**5.31 / 4.93e7)  # Eq. 25
    return float(0.208 * f_wind * f_fine)  # Eq. 26


def buildup_index(dmc: float, dc: float) -> float:
    """Eqs. 27-28. Total fuel available to the fire."""
    denominator = dmc + 0.4 * dc
    if denominator <= 0.0:
        # Both codes at zero — a saturated landscape. Van Wagner's Eq. 27
        # divides by this sum, so the degenerate case is handled here rather
        # than left to raise on a rain-soaked cell.
        return 0.0
    if dmc <= 0.4 * dc:
        return max(0.8 * dmc * dc / denominator, 0.0)  # Eq. 27
    bui = dmc - (1.0 - 0.8 * dc / denominator) * (0.92 + (0.0114 * dmc) ** 1.7)  # Eq. 28
    return float(max(bui, 0.0))


def fire_weather_index(isi: float, bui: float) -> float:
    """Eqs. 29-31. The published index: intensity of a spreading fire."""
    if bui <= 80.0:  # Eq. 29
        f_duff = 0.626 * bui**0.809 + 2.0
    else:
        f_duff = 1000.0 / (25.0 + 108.64 * math.exp(-0.023 * bui))
    b = 0.1 * isi * f_duff  # Eq. 30
    if b <= 1.0:
        return float(max(b, 0.0))
    return float(math.exp(2.72 * (0.434 * math.log(b)) ** 0.647))  # Eq. 31


def advance(
    state: FwiState,
    *,
    month: int,
    temperature_c: float,
    relative_humidity_pct: float,
    wind_speed_kmh: float,
    rain_24h_mm: float,
    params: FwiParams,
) -> FwiOutputs:
    """One day of the chain: yesterday's codes plus today's noon reading."""
    if not 1 <= month <= 12:
        raise ValueError(f"month must be in 1..12, got {month}")
    idx = month - 1
    ffmc = fine_fuel_moisture_code(
        state.ffmc,
        temperature_c=temperature_c,
        relative_humidity_pct=relative_humidity_pct,
        wind_speed_kmh=wind_speed_kmh,
        rain_24h_mm=rain_24h_mm,
    )
    dmc = duff_moisture_code(
        state.dmc,
        temperature_c=temperature_c,
        relative_humidity_pct=relative_humidity_pct,
        rain_24h_mm=rain_24h_mm,
        day_length=params.day_length_dmc[idx],
    )
    dc = drought_code(
        state.dc,
        temperature_c=temperature_c,
        rain_24h_mm=rain_24h_mm,
        day_length=params.day_length_dc[idx],
    )
    isi = initial_spread_index(ffmc, wind_speed_kmh=wind_speed_kmh)
    bui = buildup_index(dmc, dc)
    return FwiOutputs(
        state=FwiState(ffmc=ffmc, dmc=dmc, dc=dc),
        isi=isi,
        bui=bui,
        fwi=fire_weather_index(isi, bui),
    )
