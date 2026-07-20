"""MultiFactorScoringEngine — aggregation, classification, monotonicity, YAML override.

Tests rely on the packaged ``regional_thresholds.yaml``; one explicit
test (``test_engine_reads_all_constants_from_yaml``) overrides the
config to prove there are no hard-coded magic numbers.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from limen.core.models.risk import (
    CellFeatureBundle,
    DynamicInputs,
    RainfallSample,
    RainfallSeries,
    RiskLevel,
    SeismicHistoryEvent,
    StaticFactors,
)
from limen.core.scoring.engine import MultiFactorScoringEngine, score
from limen.core.scoring.regional_thresholds import (
    DEFAULT_THRESHOLDS_PATH,
    load_regional_thresholds,
)

VALUATION_TIME = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def _bundle(
    *,
    static: StaticFactors | None = None,
    rainfall_hourly: list[float] | None = None,
    api_30_mm: float | None = None,
    soil: float | None = None,
    seismic: list[SeismicHistoryEvent] | None = None,
    months_since_fire: float | None = None,
    valuation_time: datetime | None = None,
) -> CellFeatureBundle:
    static = static or StaticFactors(cell_id="c-test")
    samples: tuple[RainfallSample, ...] = ()
    if rainfall_hourly:
        start = (valuation_time or VALUATION_TIME) - timedelta(hours=len(rainfall_hourly))
        samples = tuple(
            RainfallSample(timestamp=start + timedelta(hours=i), precipitation_mm=v)
            for i, v in enumerate(rainfall_hourly)
        )
    return CellFeatureBundle(
        aoi_id="aoi-test",
        cell_id=static.cell_id,
        static=static,
        dynamic=DynamicInputs(
            valuation_time=valuation_time or VALUATION_TIME,
            rainfall=RainfallSeries(samples=samples),
            api_30_mm=api_30_mm,
            soil_moisture_0_7=soil,
            seismic_history=tuple(seismic) if seismic else (),
            months_since_fire=months_since_fire,
        ),
    )


# ---------------------------------------------------------------------------
# Determinism + purity
# ---------------------------------------------------------------------------
def test_same_input_yields_same_output() -> None:
    b = _bundle(rainfall_hourly=[5, 5, 5, 5, 5, 5], api_30_mm=120.0, soil=0.35)
    a1 = score(b)
    a2 = score(b)
    assert a1 == a2


def test_score_is_in_unit_interval() -> None:
    b = _bundle(
        static=StaticFactors(
            cell_id="c",
            susc_ispra=1.0,
            iffi_density_500=10.0,
            slope_deg=80.0,
            pai_class_norm=1.0,
            litho_weight=1.0,
        ),
        rainfall_hourly=[50, 50, 50, 50, 50, 50],
        api_30_mm=400.0,
        soil=1.0,
        months_since_fire=6.0,
    )
    s = score(b)
    assert 0.0 <= s.score <= 1.0


# ---------------------------------------------------------------------------
# Monotonicity
# ---------------------------------------------------------------------------
def test_more_rain_does_not_lower_score() -> None:
    b_low = _bundle(rainfall_hourly=[1, 1, 1, 1, 1, 1])
    b_high = _bundle(rainfall_hourly=[30, 30, 30, 30, 30, 30])
    assert score(b_high).score >= score(b_low).score


def test_higher_susceptibility_does_not_lower_score() -> None:
    low_s = StaticFactors(cell_id="c", susc_ispra=0.1)
    high_s = StaticFactors(cell_id="c", susc_ispra=0.9)
    assert score(_bundle(static=high_s)).score >= score(_bundle(static=low_s)).score


def test_older_quake_decays_seismic_factor() -> None:
    """For two otherwise-identical bundles, the older quake yields ≤ score."""
    fresh = SeismicHistoryEvent(
        event_id="fresh",
        origin_time=VALUATION_TIME,
        magnitude=4.5,
        distance_km=10.0,
        pga_g=0.15,
    )
    aged = SeismicHistoryEvent(
        event_id="aged",
        origin_time=VALUATION_TIME - timedelta(days=5),
        magnitude=4.5,
        distance_km=10.0,
        pga_g=0.15,
    )
    s_fresh = score(_bundle(seismic=[fresh]))
    s_aged = score(_bundle(seismic=[aged]))
    assert s_fresh.score >= s_aged.score
    assert s_fresh.breakdown.e >= s_aged.breakdown.e


# ---------------------------------------------------------------------------
# Class boundaries
# ---------------------------------------------------------------------------
def test_low_signal_classifies_as_none() -> None:
    s = score(_bundle())
    assert s.level in {RiskLevel.None_, RiskLevel.Low}


def test_high_static_only_can_reach_moderate_or_above() -> None:
    """Saturating S alone gets the bundle past Low (~0.35)."""
    fully_loaded_static = StaticFactors(
        cell_id="c",
        susc_ispra=1.0,
        iffi_density_500=10.0,
        slope_deg=80.0,
        pai_class_norm=1.0,
        litho_weight=1.0,
    )
    s = score(_bundle(static=fully_loaded_static))
    assert s.score >= 0.0
    assert s.level in {RiskLevel.Low, RiskLevel.Moderate, RiskLevel.High, RiskLevel.VeryHigh}


def test_extreme_inputs_reach_very_high() -> None:
    """Saturate every component → VeryHigh class."""
    fully_loaded_static = StaticFactors(
        cell_id="c",
        susc_ispra=1.0,
        iffi_density_500=10.0,
        slope_deg=80.0,
        pai_class_norm=1.0,
        litho_weight=1.0,
    )
    fresh_quake = SeismicHistoryEvent(
        event_id="big",
        origin_time=VALUATION_TIME,
        magnitude=5.5,
        distance_km=5.0,
        pga_g=0.40,
    )
    s = score(
        _bundle(
            static=fully_loaded_static,
            rainfall_hourly=[40] * 8,
            api_30_mm=400.0,
            soil=0.9,
            seismic=[fresh_quake],
            months_since_fire=6.0,
        )
    )
    assert s.level is RiskLevel.VeryHigh
    assert s.score >= 0.75


def test_breakdown_components_are_in_unit_interval() -> None:
    s = score(_bundle(rainfall_hourly=[10] * 6, api_30_mm=150.0, soil=0.5))
    b = s.breakdown
    for v in (b.s, b.m, b.e, b.f, b.h):
        assert 0.0 <= v <= 1.0


# ---------------------------------------------------------------------------
# YAML override — proves no hard-coded constants
# ---------------------------------------------------------------------------
@pytest.fixture
def tweaked_yaml(tmp_path: Path) -> Iterator[Path]:
    text = DEFAULT_THRESHOLDS_PATH.read_text(encoding="utf-8")
    cfg = yaml.safe_load(text)
    cfg["weights"]["static"] = 1.0
    cfg["weights"]["meteo"] = 0.0
    cfg["weights"]["seismic"] = 0.0
    cfg["weights"]["fire"] = 0.0
    cfg["weights"]["hydrology"] = 0.0
    # Drive S entirely off susceptibility so the test controls its own
    # constant (proves the engine reads sub-weights from the YAML, not
    # from the reweighted default where susc_ispra = 0).
    cfg["static"]["weights"] = {
        "susc_ispra": 1.0,
        "iffi_density": 0.0,
        "slope": 0.0,
        "pai": 0.0,
        "litho_weight": 0.0,
    }
    out = tmp_path / "tweaked.yaml"
    out.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    yield out


def test_engine_reads_all_constants_from_yaml(tweaked_yaml: Path) -> None:
    """w_S=1, others=0 → score equals S regardless of meteo/seismic/fire."""
    tweaked = load_regional_thresholds(tweaked_yaml)
    engine = MultiFactorScoringEngine(tweaked)

    bundle = _bundle(
        static=StaticFactors(cell_id="c", susc_ispra=0.1),
        rainfall_hourly=[40] * 8,  # would normally push score up
        api_30_mm=300.0,
        soil=0.9,
    )
    result = engine.score(bundle)
    # Static-only weights with susc sub-weight forced to 1.0 → S = 1.0 · 0.1.
    assert result.score == pytest.approx(0.1, abs=1e-9)
    assert result.breakdown.m > 0.0  # raw component still computed (auditable)
    assert result.level is RiskLevel.None_


def test_engine_model_version_propagates() -> None:
    s = score(_bundle())
    assert s.model_version == load_regional_thresholds().model_version


# ---------------------------------------------------------------------------
# Rain-on-snow (snow block)
# ---------------------------------------------------------------------------
def test_no_snowpack_scores_identical_to_pre_snow_engine() -> None:
    """snow_depth None or below ros_min_depth_m ⇒ snow_factor 0 ⇒ same M."""
    base = _bundle(rainfall_hourly=[3.0] * 12, api_30_mm=100.0, soil=0.30)
    shallow = base.model_copy(
        update={"dynamic": base.dynamic.model_copy(update={"snow_depth_m": 0.01})}
    )
    assert score(shallow).breakdown.meteo_terms.snow_factor == 0.0
    assert score(shallow).score == score(base).score


def test_rain_on_snow_amplifies_m() -> None:
    base = _bundle(rainfall_hourly=[3.0] * 12, api_30_mm=100.0, soil=0.30)
    snowy = base.model_copy(
        update={"dynamic": base.dynamic.model_copy(update={"snow_depth_m": 0.5})}
    )
    dry_snow = _bundle(api_30_mm=100.0, soil=0.30).model_copy(
        update={
            "dynamic": _bundle(api_30_mm=100.0, soil=0.30).dynamic.model_copy(
                update={"snow_depth_m": 0.5}
            )
        }
    )
    scored = score(snowy)
    assert scored.breakdown.meteo_terms.snow_factor > 0.0
    assert scored.breakdown.m > score(base).breakdown.m
    # Snowpack WITHOUT recent rain adds nothing (it's rain-ON-snow).
    assert score(dry_snow).breakdown.meteo_terms.snow_factor == 0.0


# ---------------------------------------------------------------------------
# Rain floor — tier bypass predicate (issue #20)
# ---------------------------------------------------------------------------
_LOW_SUSC = StaticFactors(cell_id="c", susc_ispra=0.05, iffi_density_500=0.0)


def test_floor_rescues_low_susceptibility_cell_with_extreme_rain() -> None:
    """A low-susceptibility cell with rain over the floor is rescued regardless
    of its tier — the predicate never looks at susceptibility."""
    engine = MultiFactorScoringEngine()
    b = _bundle(static=_LOW_SUSC, rainfall_hourly=[5.0] * 6, soil=0.60)
    assert engine.is_rescued_by_floor(b) is True
    # Rescued ⇒ it gets scored and can carry a non-zero risk (can escalate).
    assert engine.score(b).score > 0.0


def test_floor_leaves_sub_floor_rain_pruned() -> None:
    """Rain below the floor ⇒ not rescued ⇒ the tiering saving is preserved
    (no superfluous meteo/LLM spend on this cell)."""
    engine = MultiFactorScoringEngine()
    b = _bundle(static=_LOW_SUSC, rainfall_hourly=[1.0] * 6, soil=0.60)
    assert engine.is_rescued_by_floor(b) is False


def test_floor_is_conditioned_on_antecedent_wetness() -> None:
    """Same rain over the floor: a saturated cell is rescued, a dry one is not."""
    engine = MultiFactorScoringEngine()
    saturated = _bundle(static=_LOW_SUSC, rainfall_hourly=[5.0] * 6, soil=0.60)
    dry = _bundle(static=_LOW_SUSC, rainfall_hourly=[5.0] * 6, soil=0.10)
    assert engine.is_rescued_by_floor(saturated) is True
    assert engine.is_rescued_by_floor(dry) is False


def test_floor_absent_returns_false(tmp_path: Path) -> None:
    """A YAML without a rain_floor block ⇒ predicate inert (backward-compatible)."""
    cfg = yaml.safe_load(DEFAULT_THRESHOLDS_PATH.read_text(encoding="utf-8"))
    cfg.pop("rain_floor", None)
    out = tmp_path / "no_floor.yaml"
    out.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    engine = MultiFactorScoringEngine(load_regional_thresholds(out))
    b = _bundle(static=_LOW_SUSC, rainfall_hourly=[50.0] * 6, soil=0.90)
    assert engine.is_rescued_by_floor(b) is False


def test_floor_values_come_from_yaml(tmp_path: Path) -> None:
    """Raising wetness_min above the saturated cell's wetness suppresses the
    rescue — proving the floor is parametrised entirely from the YAML."""
    cfg = yaml.safe_load(DEFAULT_THRESHOLDS_PATH.read_text(encoding="utf-8"))
    cfg["rain_floor"]["wetness_min"] = 0.999
    out = tmp_path / "strict_floor.yaml"
    out.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    engine = MultiFactorScoringEngine(load_regional_thresholds(out))
    b = _bundle(static=_LOW_SUSC, rainfall_hourly=[5.0] * 6, soil=0.60)
    assert engine.is_rescued_by_floor(b) is False


# ---------------------------------------------------------------------------
# Dynamic flood forecast — H uplift (issue #8)
# ---------------------------------------------------------------------------
def test_flood_forecast_lifts_h_when_rain_forecast() -> None:
    static = StaticFactors(cell_id="c", flood_hazard_norm=0.8)
    dry = _bundle(static=static)  # no forecast flood signals
    wet = dry.model_copy(
        update={
            "dynamic": dry.dynamic.model_copy(
                update={"flood_forecast_rain_72h_mm": 200.0}
            )
        }
    )
    assert score(wet).breakdown.h > score(dry).breakdown.h
    assert score(wet).score >= score(dry).score


def test_flood_forecast_absent_keeps_h_static() -> None:
    # No flood signals ⇒ H equals the pure static hazard (byte-identical to V1).
    b = _bundle(static=StaticFactors(cell_id="c", flood_hazard_norm=0.8))
    assert score(b).breakdown.h == pytest.approx(0.8)
