"""MLScoringEngine — SHAP-backed component breakdown."""

from __future__ import annotations

from typing import Any

import pytest

from limen.core.scoring.ml_engine import (
    _component_attribution,
    _component_for,
    _MLArtefacts,
)


def _artefacts(*, names: list[str], explainer: Any = None) -> _MLArtefacts:
    return _MLArtefacts(
        model_uri="test://m",
        model_version="v0",
        booster=object(),
        calibrator=None,
        explainer=explainer,
        feature_names=names,
    )


# ---------------------------------------------------------------------------
# _component_for — prefix → letter
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "name,expected",
    [
        ("static.susc_ispra", "S"),
        ("static.slope_deg", "S"),
        ("insar.velocity_mmy", "S"),
        ("meteo.rainfall_72h", "M"),
        ("rainfall.api_30", "M"),
        ("api.soil_moisture", "M"),
        ("caine.excess", "M"),
        ("seismic.pga_max", "E"),
        ("fire.months_since", "F"),
        ("post_fire.factor", "F"),
        ("hydrology.runoff", "H"),
        ("kinematic.velocity", "K"),
        ("displacement.daily", "K"),
        ("velocity.average", "K"),
        ("an_unknown_feature", "S"),  # default fallback
    ],
)
def test_component_for(name: str, expected: str) -> None:
    assert _component_for(name) == expected


# ---------------------------------------------------------------------------
# _component_attribution
# ---------------------------------------------------------------------------
def test_attribution_returns_six_components() -> None:
    art = _artefacts(names=["static.x", "meteo.y"])
    out = _component_attribution(art, feature_row=[0.3, 0.7], total=0.5)
    assert set(out.keys()) == {"S", "M", "E", "F", "H", "K"}


def test_attribution_zero_total_returns_zero_components() -> None:
    art = _artefacts(names=["static.x"])
    out = _component_attribution(art, feature_row=[0.5], total=0.0)
    assert all(v == 0.0 for v in out.values())


def test_attribution_renormalises_to_total_when_using_raw_magnitudes() -> None:
    """No SHAP available → use the feature magnitudes themselves, rescaled."""
    art = _artefacts(names=["static.a", "meteo.b", "seismic.c"])
    out = _component_attribution(art, feature_row=[0.4, 0.4, 0.2], total=0.5)
    total = sum(out.values())
    # Components may be individually clamped to [0, 1] but the sum must
    # match the target to a tight tolerance.
    assert total == pytest.approx(0.5, abs=1e-6)
    # The static + meteo components dominate the seismic one.
    assert out["S"] > out["E"]
    assert out["M"] > out["E"]


def test_attribution_no_feature_schema_returns_pure_static() -> None:
    """Resolver fallback path: empty feature_names → all weight on S."""
    art = _artefacts(names=[])
    out = _component_attribution(art, feature_row=[], total=0.42)
    assert out["S"] == pytest.approx(0.42)
    assert out["M"] == 0.0
    assert out["K"] == 0.0


def test_attribution_uses_shap_when_available() -> None:
    """A stub explainer drives the attribution if SHAP returns signed values."""

    class _Stub:
        def __init__(self, contributions: list[float]) -> None:
            self.contributions = contributions
            self.calls = 0

        def shap_values(self, arr: Any) -> Any:
            self.calls += 1
            return [self.contributions]

    # Two static features + one seismic — SHAP says the seismic one
    # carried 60% of the |contribution|, so S < E in the output.
    contributions = [0.1, -0.1, 0.6]
    art = _artefacts(
        names=["static.a", "static.b", "seismic.c"],
        explainer=_Stub(contributions),
    )
    out = _component_attribution(art, feature_row=[0.1, 0.2, 0.9], total=0.8)
    # Sum still matches the calibrated probability.
    assert sum(out.values()) == pytest.approx(0.8, abs=1e-6)
    # Seismic dominates because SHAP gave it the largest |contribution|.
    assert out["E"] > out["S"]


def test_attribution_handles_mismatched_row_length() -> None:
    """A feature_row shorter than the schema falls back to the resolver default."""
    art = _artefacts(names=["static.a", "static.b", "static.c"])
    out = _component_attribution(art, feature_row=[0.5], total=0.6)
    # Mismatch → pure-static fallback as if no schema was loaded.
    assert out["S"] == pytest.approx(0.6)
    assert out["M"] == 0.0
