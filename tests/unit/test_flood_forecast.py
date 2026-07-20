"""Dynamic flood factor — pure scoring logic + schema (issue #8)."""

from __future__ import annotations

from datetime import UTC, datetime

from limen.core.models.risk import DynamicInputs
from limen.core.scoring.flood_forecast import flood_forecast_bonus
from limen.core.scoring.regional_thresholds import (
    FloodForecastBlock,
    FloodForecastMacroregion,
    load_regional_thresholds,
)

_CFG = FloodForecastBlock(
    hazard_uplift=0.5,
    discharge_ratio_center=2.0,
    discharge_ratio_steepness=0.8,
    macroregions={"italy_default": FloodForecastMacroregion(center_mm=90.0, steepness_mm=35.0)},
)


def _bonus(**over: float | None) -> float:
    kw: dict[str, float | None] = {
        "rain_72h_mm": None,
        "river_discharge_ratio": None,
        "coastal_surge_norm": None,
        "flood_hazard_norm": 0.8,
    }
    kw.update(over)
    return flood_forecast_bonus(**kw, macroregion="italy_default", cfg=_CFG)  # type: ignore[arg-type]


def test_no_hazard_gives_zero() -> None:
    assert _bonus(rain_72h_mm=200.0, flood_hazard_norm=None) == 0.0
    assert _bonus(rain_72h_mm=200.0, flood_hazard_norm=0.0) == 0.0


def test_all_signals_absent_gives_zero() -> None:
    assert _bonus() == 0.0


def test_pluvial_uplift() -> None:
    # 200 mm ≫ centre 90 → sigmoid≈1 → ≈ 0.8·0.5·1
    assert 0.35 < _bonus(rain_72h_mm=200.0) <= 0.4


def test_fluvial_signal_from_discharge_ratio() -> None:
    assert _bonus(river_discharge_ratio=4.0) > 0.35  # 4 ≫ centre 2


def test_coastal_signal() -> None:
    assert _bonus(coastal_surge_norm=1.0) == 0.4  # 0.8·0.5·1.0


def test_takes_max_across_signals() -> None:
    weak = _bonus(rain_72h_mm=5.0)
    strong = _bonus(rain_72h_mm=5.0, coastal_surge_norm=0.9)
    assert strong > weak


def test_unknown_macroregion_falls_back_to_default() -> None:
    b = flood_forecast_bonus(
        rain_72h_mm=200.0,
        river_discharge_ratio=None,
        coastal_surge_norm=None,
        flood_hazard_norm=0.8,
        macroregion="atlantis",
        cfg=_CFG,
    )
    assert b > 0.0


def test_yaml_block_loads_from_default() -> None:
    t = load_regional_thresholds()
    assert t.flood_forecast is not None
    mr = t.flood_forecast.macroregions["italy_default"]
    assert mr.center_mm > 0 and mr.steepness_mm > 0
    assert t.flood_forecast.discharge_ratio_center > 0


def test_dynamic_inputs_defaults_none() -> None:
    d = DynamicInputs(valuation_time=datetime(2026, 6, 1, tzinfo=UTC))
    assert d.flood_forecast_rain_72h_mm is None
    assert d.river_discharge_ratio is None
    assert d.coastal_surge_norm is None


def test_flood_forecast_disabled_by_default() -> None:
    from limen.config.settings import Settings

    assert Settings().enable_flood_forecast is False
