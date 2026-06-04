"""V2.1 — EGMS scatterer → per-cell aggregation."""

from __future__ import annotations

from datetime import date

import pytest
from shapely.geometry import Polygon

from limen.integrations.egms.aggregate import aggregate_scatterers_to_cells
from limen.integrations.egms.client import ScattererPoint


def _square(lon: float, lat: float, edge: float = 0.01) -> Polygon:
    return Polygon(
        [
            (lon, lat),
            (lon + edge, lat),
            (lon + edge, lat + edge),
            (lon, lat + edge),
            (lon, lat),
        ]
    )


def test_aggregation_assigns_each_point_to_exactly_one_cell() -> None:
    cell_a = _square(16.86, 41.12, edge=0.02)
    cell_b = _square(16.90, 41.12, edge=0.02)
    cells = {"a": cell_a, "b": cell_b}
    # Points placed well inside each cell — shapely `contains` excludes
    # boundaries so we stay > epsilon away from the edges.
    scatterers = [
        ScattererPoint(
            lon=16.865,
            lat=41.125,
            velocity_mmy=-3.0,
            acceleration_mmy2=0.1,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
        ),
        ScattererPoint(
            lon=16.905,
            lat=41.125,
            velocity_mmy=-8.0,
            acceleration_mmy2=0.4,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
        ),
    ]
    out = aggregate_scatterers_to_cells(scatterers=scatterers, cells=cells)
    by_id = {r.cell_id: r for r in out}
    assert by_id["a"].scatterer_count == 1
    assert by_id["b"].scatterer_count == 1
    assert by_id["a"].insar_velocity_mmy == pytest.approx(-3.0)
    assert by_id["b"].insar_velocity_mmy == pytest.approx(-8.0)


def test_empty_cells_get_zero_count_rows() -> None:
    cells = {"empty": _square(0.0, 0.0)}
    out = aggregate_scatterers_to_cells(scatterers=[], cells=cells)
    assert len(out) == 1
    assert out[0].scatterer_count == 0
    assert out[0].insar_velocity_mmy is None


def test_median_aggregation_is_robust_to_outliers() -> None:
    """Five scatterers, one wild outlier — median should ignore it."""
    cells = {"only": _square(16.86, 41.12, edge=0.1)}
    scatterers = [
        ScattererPoint(
            lon=16.87,
            lat=41.13,
            velocity_mmy=v,
            acceleration_mmy2=None,
            period_start=None,
            period_end=None,
        )
        for v in (-3.0, -2.5, -3.2, -2.8, -100.0)
    ]
    out = aggregate_scatterers_to_cells(scatterers=scatterers, cells=cells)
    assert out[0].scatterer_count == 5
    # Median of (-3.0, -2.5, -3.2, -2.8, -100.0) sorted is -3.0.
    assert out[0].insar_velocity_mmy == pytest.approx(-3.0)


def test_period_envelope_covers_all_inputs() -> None:
    cells = {"only": _square(16.86, 41.12, edge=0.1)}
    scatterers = [
        ScattererPoint(
            lon=16.87,
            lat=41.13,
            velocity_mmy=-3.0,
            acceleration_mmy2=None,
            period_start=date(2023, 6, 1),
            period_end=date(2023, 12, 31),
        ),
        ScattererPoint(
            lon=16.88,
            lat=41.14,
            velocity_mmy=-2.5,
            acceleration_mmy2=None,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 9, 30),
        ),
    ]
    out = aggregate_scatterers_to_cells(scatterers=scatterers, cells=cells)
    assert out[0].period_start == date(2023, 6, 1)
    assert out[0].period_end == date(2024, 9, 30)
