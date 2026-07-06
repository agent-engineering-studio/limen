"""V2 — dataset packing + canonical-feature ordering."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from limen.data.repos.training_samples_repo import TrainingSample
from limen.ml.dataset import CANONICAL_FEATURES, to_matrix


@pytest.fixture
def samples() -> list[TrainingSample]:
    return [
        TrainingSample(
            cell_id="c-1",
            valuation_time=datetime(2026, 1, 1, tzinfo=UTC),
            label=1,
            label_source="iffi",
            features={
                "static": {"susc_ispra": 0.6, "slope_deg": 22.0},
                "insar": {"velocity_mmy": -8.0},
            },
            split_block="b-1",
        ),
        TrainingSample(
            cell_id="c-2",
            valuation_time=datetime(2026, 1, 2, tzinfo=UTC),
            label=0,
            label_source="background",
            features={
                "static": {"susc_ispra": 0.2},
                "insar": {"velocity_mmy": None},
            },
            split_block="b-2",
        ),
    ]


def test_to_matrix_uses_canonical_ordering(samples: list[TrainingSample]) -> None:
    matrix = to_matrix(samples)
    assert matrix.feature_names == CANONICAL_FEATURES
    assert matrix.X.shape == (2, len(CANONICAL_FEATURES))
    assert matrix.y.tolist() == [1, 0]
    assert matrix.groups == ("b-1", "b-2")


def test_to_matrix_handles_missing_fields(samples: list[TrainingSample]) -> None:
    matrix = to_matrix(samples)
    susc_idx = CANONICAL_FEATURES.index("static.susc_ispra")
    twi_idx = CANONICAL_FEATURES.index("static.twi")
    assert matrix.X[0, susc_idx] == pytest.approx(0.6)
    # Missing fields project to 0.0 — no NaN propagation into the model.
    assert matrix.X[0, twi_idx] == pytest.approx(0.0)
    assert matrix.X[1, susc_idx] == pytest.approx(0.2)


def test_to_matrix_treats_none_as_zero(samples: list[TrainingSample]) -> None:
    matrix = to_matrix(samples)
    velocity_idx = CANONICAL_FEATURES.index("insar.velocity_mmy")
    # Row 1 set velocity_mmy=None explicitly → 0.0 in the matrix.
    assert matrix.X[1, velocity_idx] == pytest.approx(0.0)


def test_prune_collinear_drops_twin_keeps_canonical_first() -> None:
    import numpy as np

    from limen.ml.dataset import TrainingMatrix, prune_collinear

    rng = np.random.default_rng(7)
    a = rng.normal(size=200)
    b = a * 2.0 + 1e-9  # perfect twin of a
    c = rng.normal(size=200)
    m = TrainingMatrix(
        feature_names=("a", "b", "c"),
        X=np.column_stack([a, b, c]),
        y=np.zeros(200, dtype=int),
        groups=tuple("g" for _ in range(200)),
    )
    pruned, dropped = prune_collinear(m, threshold=0.95)
    assert pruned.feature_names == ("a", "c")
    assert dropped[0][0] == "a" and dropped[0][1] == "b"
    assert pruned.X.shape == (200, 2)


def test_prune_collinear_noop_below_threshold() -> None:
    import numpy as np

    from limen.ml.dataset import TrainingMatrix, prune_collinear

    rng = np.random.default_rng(7)
    m = TrainingMatrix(
        feature_names=("a", "b"),
        X=rng.normal(size=(100, 2)),
        y=np.zeros(100, dtype=int),
        groups=tuple("g" for _ in range(100)),
    )
    pruned, dropped = prune_collinear(m, threshold=0.95)
    assert pruned is m and dropped == []
