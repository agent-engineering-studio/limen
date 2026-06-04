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
