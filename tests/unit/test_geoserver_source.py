"""Unit tests for the GeoServer-source pure helpers + reweighted S."""

from __future__ import annotations

import pytest

from limen.core.scoring.regional_thresholds import load_regional_thresholds
from limen.integrations.geoserver_source.loader import _pai_class_token, _region_token


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Aree di Attenzione AA", "AA"),
        ("Moderata P1", "P1"),
        ("Media P2", "P2"),
        ("Elevata P3", "P3"),
        ("Molto elevata P4", "P4"),
        ("elevata p3", "P3"),
        ("qualcosa senza classe", None),
        ("", None),
        (None, None),
    ],
)
def test_pai_class_token(value: str | None, expected: str | None) -> None:
    assert _pai_class_token(value) == expected


@pytest.mark.parametrize(
    ("aoi_id", "expected"),
    [
        ("it-puglia", "puglia"),
        ("it-basilicata", "basilicata"),
        ("puglia", "puglia"),
        ("IT-Valle-d-Aosta", "valle_d_aosta"),
    ],
)
def test_region_token(aoi_id: str, expected: str) -> None:
    assert _region_token(aoi_id) == expected


def test_static_weights_reweighted_and_gate_disabled() -> None:
    """Susceptibility is dropped from S; the S↔ISPRA gate is disabled."""
    t = load_regional_thresholds()
    w = t.static.weights
    assert w.susc_ispra == 0.0
    # Weight redistributed onto the GeoServer-sourced inputs + slope.
    assert w.iffi_density == pytest.approx(0.375)
    assert w.slope == pytest.approx(0.30)
    assert w.pai == pytest.approx(0.225)
    assert t.calibration.s_vs_ispra_correlation_min is None
