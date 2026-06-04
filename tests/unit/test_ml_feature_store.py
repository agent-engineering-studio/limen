"""V2 — feature store spatial-block grid + CV partition + bundle parity."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from limen.ml.feature_store import (
    SpatialBlockGrid,
    features_to_bundle,
    spatial_block_folds,
)


# ---------------------------------------------------------------------------
# SpatialBlockGrid
# ---------------------------------------------------------------------------
def test_grid_assigns_neighbours_to_same_block() -> None:
    grid = SpatialBlockGrid(edge_deg=0.5)
    assert grid.block_for(16.86, 41.12) == grid.block_for(16.92, 41.17)


def test_grid_separates_distant_points() -> None:
    grid = SpatialBlockGrid(edge_deg=0.5)
    assert grid.block_for(16.86, 41.12) != grid.block_for(18.00, 41.12)


def test_grid_is_deterministic() -> None:
    grid = SpatialBlockGrid(edge_deg=0.5)
    assert grid.block_for(16.86, 41.12) == grid.block_for(16.86, 41.12)


# ---------------------------------------------------------------------------
# Spatial-block CV folds
# ---------------------------------------------------------------------------
def test_folds_are_disjoint_and_cover_all_blocks() -> None:
    blocks = [f"b-{i}" for i in range(13)]
    folds = spatial_block_folds(blocks, k=5)
    assert len(folds) == 5
    flat = [b for fold in folds for b in fold]
    assert sorted(flat) == sorted(blocks)
    # No block appears in two folds
    assert len(set(flat)) == len(flat)


def test_folds_are_balanced_within_one() -> None:
    blocks = [f"b-{i}" for i in range(20)]
    folds = spatial_block_folds(blocks, k=5)
    sizes = [len(f) for f in folds]
    assert max(sizes) - min(sizes) <= 1


def test_folds_deterministic_with_same_seed() -> None:
    blocks = [f"b-{i}" for i in range(15)]
    a = spatial_block_folds(blocks, k=4, rng_seed=7)
    b = spatial_block_folds(blocks, k=4, rng_seed=7)
    assert a == b


def test_folds_reject_k_lt_2() -> None:
    with pytest.raises(ValueError):
        spatial_block_folds(["a", "b"], k=1)


# ---------------------------------------------------------------------------
# features_to_bundle — train/serve parity
# ---------------------------------------------------------------------------
def test_features_to_bundle_reconstructs_static_factors() -> None:
    features = {
        "static": {
            "susc_ispra": 0.6,
            "slope_deg": 25.0,
            "pai_class_norm": 0.4,
            "litho_weight": 0.3,
        },
    }
    bundle = features_to_bundle(
        cell_id="aoi|0|0",
        aoi_id="aoi",
        valuation_time=datetime(2026, 1, 1, tzinfo=UTC),
        features=features,
    )
    assert bundle.static.susc_ispra == pytest.approx(0.6)
    assert bundle.static.slope_deg == pytest.approx(25.0)
    assert bundle.static.cell_id == "aoi|0|0"


def test_features_to_bundle_handles_missing_static() -> None:
    bundle = features_to_bundle(
        cell_id="aoi|0|0",
        aoi_id="aoi",
        valuation_time=datetime(2026, 1, 1, tzinfo=UTC),
        features={},
    )
    assert bundle.static.susc_ispra is None
    assert bundle.dynamic.rainfall.samples == ()
