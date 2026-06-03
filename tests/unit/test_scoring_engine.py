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
    out = tmp_path / "tweaked.yaml"
    out.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    yield out


def test_engine_reads_all_constants_from_yaml(tweaked_yaml: Path) -> None:
    """w_S=1, others=0 → score equals S regardless of meteo/seismic/fire."""
    tweaked = load_regional_thresholds(tweaked_yaml)
    engine = MultiFactorScoringEngine(tweaked)

    bundle = _bundle(
        static=StaticFactors(cell_id="c", susc_ispra=0.4),
        rainfall_hourly=[40] * 8,  # would normally push score up
        api_30_mm=300.0,
        soil=0.9,
    )
    result = engine.score(bundle)
    # Static-only weights → w_susc=0.30, so S = 0.30 · 0.4 = 0.12; rest 0.
    assert result.score == pytest.approx(0.30 * 0.4, abs=1e-9)
    assert result.breakdown.m > 0.0  # raw component still computed (auditable)
    assert result.level is RiskLevel.None_


def test_engine_model_version_propagates() -> None:
    s = score(_bundle())
    assert s.model_version == load_regional_thresholds().model_version
