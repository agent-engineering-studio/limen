"""Per-cell rainfall assignment in the bundle assembler (pure, no I/O)."""

from __future__ import annotations

from datetime import UTC, datetime

from limen.core.features.assembler import assemble_bundles
from limen.core.models.context import MonitoringContext
from limen.core.models.risk import RainfallSample

_T0 = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def _sample(mm: float) -> RainfallSample:
    return RainfallSample(timestamp=_T0, precipitation_mm=mm)


def _ctx(**overrides: object) -> MonitoringContext:
    base: dict[str, object] = {
        "aoi_id": "it-test",
        "valuation_time": _T0,
        "cell_ids": ("c-west", "c-east"),
        "cell_centroids": {"c-west": (16.0, 40.0), "c-east": (16.5, 40.0)},
        "meteo_samples": (_sample(1.0),),
    }
    base.update(overrides)
    return MonitoringContext.model_validate(base)


def test_each_cell_gets_its_nearest_node_series() -> None:
    ctx = _ctx(
        rain_nodes=((16.0, 40.0), (16.5, 40.0)),
        rainfall_by_node=((_sample(10.0),), (_sample(50.0),)),
    )
    by_cell = {
        b.cell_id: b.dynamic.rainfall.samples[0].precipitation_mm for b in assemble_bundles(ctx)
    }
    assert by_cell == {"c-west": 10.0, "c-east": 50.0}


def test_no_grid_falls_back_to_aoi_series() -> None:
    by_cell = {
        b.cell_id: b.dynamic.rainfall.samples[0].precipitation_mm for b in assemble_bundles(_ctx())
    }
    assert by_cell == {"c-west": 1.0, "c-east": 1.0}


def test_empty_node_series_and_missing_centroid_fall_back() -> None:
    ctx = _ctx(
        cell_centroids={"c-west": (16.0, 40.0)},  # c-east has no centroid
        rain_nodes=((16.0, 40.0), (16.5, 40.0)),
        rainfall_by_node=((), (_sample(50.0),)),  # west node series empty
    )
    by_cell = {
        b.cell_id: b.dynamic.rainfall.samples[0].precipitation_mm for b in assemble_bundles(ctx)
    }
    # west: nearest node empty → AOI fallback; east: no centroid → AOI fallback.
    assert by_cell == {"c-west": 1.0, "c-east": 1.0}
