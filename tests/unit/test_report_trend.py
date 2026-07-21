"""Per-zone report trend — pure SVG + points (issue #42)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from limen.report.trend import trend_points, trend_svg

_T0 = datetime(2026, 7, 20, 0, 0, tzinfo=UTC)
_OBS = [(_T0, 0.30), (_T0 + timedelta(hours=24), 0.36)]
_FC = [(_T0 + timedelta(hours=48), 0.42), (_T0 + timedelta(hours=72), 0.55)]


def test_trend_svg_has_observed_and_forecast_paths() -> None:
    svg = trend_svg(_OBS, _FC)
    assert svg.startswith("<svg")
    # two polylines: observed solid + forecast dashed
    assert svg.count("<path") == 2
    assert "stroke-dasharray" in svg  # forecast + now marker
    assert 'role="img"' in svg


def test_trend_svg_empty_when_no_data() -> None:
    assert trend_svg([], []) == ""


def test_trend_svg_forecast_only_still_draws() -> None:
    svg = trend_svg([], _FC)
    assert svg.startswith("<svg")
    assert svg.count("<path") == 1


def test_trend_points_are_serialisable_and_rounded() -> None:
    pts = trend_points(_OBS, _FC)
    assert pts["observed"][0] == [_T0.isoformat(), 0.3]
    assert len(pts["forecast"]) == 2
    assert pts["forecast"][-1][1] == 0.55
