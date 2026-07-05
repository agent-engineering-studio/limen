"""Rain-feature enrichment: pure aggregate + baseline-bundle reconstruction."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from limen.ml.feature_store import features_to_bundle
from limen.ml.rain_features import compute_rain_aggregates

_T0 = datetime(2009, 3, 7, 12, 0, tzinfo=UTC)


def test_aggregates_respect_windows() -> None:
    series = [
        (_T0 - timedelta(hours=2), 5.0),     # in 24h
        (_T0 - timedelta(hours=30), 10.0),   # in 72h, not 24h
        (_T0 - timedelta(days=10), 20.0),    # in 30d only
        (_T0 - timedelta(days=40), 99.0),    # fuori finestra
        (_T0 + timedelta(hours=1), 99.0),    # futuro: escluso
    ]
    r = compute_rain_aggregates(series, _T0)
    assert r == {
        "rain_24h_mm": 5.0,
        "rain_72h_mm": 15.0,
        "rain_30d_mm": 35.0,
        "max_i_24h_mmh": 5.0,
    }


def test_baseline_bundle_rebuilds_the_same_water() -> None:
    features = {
        "static": {"slope_deg": 20.0},
        "rain": {"rain_24h_mm": 24.0, "rain_72h_mm": 72.0, "rain_30d_mm": 120.0},
    }
    b = features_to_bundle(
        cell_id="c", aoi_id="a", valuation_time=_T0, features=features
    )
    total = sum(s.precipitation_mm for s in b.dynamic.rainfall.samples)
    last24 = sum(
        s.precipitation_mm
        for s in b.dynamic.rainfall.samples
        if s.timestamp >= _T0 - timedelta(hours=24)
    )
    assert abs(total - 72.0) < 1e-6
    assert abs(last24 - 24.0) < 1e-6
    assert b.dynamic.api_30_mm == 120.0


def test_no_rain_block_degrades_to_empty_series() -> None:
    b = features_to_bundle(cell_id="c", aoi_id="a", valuation_time=_T0, features={})
    assert b.dynamic.rainfall.samples == ()
    assert b.dynamic.api_30_mm is None
