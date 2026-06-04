"""Engine H (hydrology) component — driven by ``flood_hazard_norm``."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from limen.core.models.risk import (
    CellFeatureBundle,
    DynamicInputs,
    RainfallSeries,
    StaticFactors,
)
from limen.core.scoring.engine import score
from limen.core.scoring.regional_thresholds import load_regional_thresholds

VALUATION_TIME = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def _bundle(flood_hazard_norm: float | None) -> CellFeatureBundle:
    static = StaticFactors(
        cell_id="c-h",
        susc_ispra=0.0,
        flood_hazard_norm=flood_hazard_norm,
    )
    return CellFeatureBundle(
        aoi_id="aoi",
        cell_id="c-h",
        static=static,
        dynamic=DynamicInputs(valuation_time=VALUATION_TIME, rainfall=RainfallSeries()),
    )


def test_h_is_zero_when_flood_norm_unset() -> None:
    """V1 baseline behaviour — unset flood_hazard_norm keeps H = 0."""
    result = score(_bundle(None))
    assert result.breakdown.h == 0.0


def test_h_picks_up_flood_hazard_norm_when_set() -> None:
    """A cell with a populated flood class contributes to the total."""
    result = score(_bundle(0.5))
    assert result.breakdown.h == pytest.approx(0.5)


def test_h_clamped_to_unit_interval() -> None:
    """The DB constraint caps the column at 1.0; the engine clamps defensively."""
    # The Pydantic schema rejects > 1.0; use the upper bound directly.
    result = score(_bundle(1.0))
    assert result.breakdown.h == pytest.approx(1.0)


def test_flood_contributes_to_aggregate_score() -> None:
    """A high flood norm raises the total score by exactly w_hydrology."""
    low = score(_bundle(0.0))
    high = score(_bundle(1.0))
    assert high.score > low.score
    # The delta is exactly w_hydrology * 1.0 — every other component is
    # identical between the two bundles.
    t = load_regional_thresholds()
    assert high.score - low.score == pytest.approx(t.weights.hydrology, abs=1e-6)
