"""V2 — training pipeline behaviour without a real dataset."""

from __future__ import annotations

import pytest

from limen.ml.train import (
    TrainResult,
    _check_promotion,
    _need_minimum_samples,
    run_training,
)


@pytest.fixture
def settings():  # type: ignore[no-untyped-def]
    from limen.config.settings import Settings

    return Settings.model_validate({})


def test_promotion_gate_blocks_when_ml_loses(settings) -> None:  # type: ignore[no-untyped-def]
    """ML below baseline → no promotion even if absolute floors clear."""
    assert (
        _check_promotion(
            settings=settings,
            ml_auc_pr=0.60,
            ml_brier=0.10,
            baseline_auc_pr=0.65,  # baseline beats ML
            hit_rate=0.80,
            far=0.20,
            lead_time_hours=24.0,
        )
        is False
    )


def test_promotion_gate_blocks_on_far(settings) -> None:  # type: ignore[no-untyped-def]
    assert (
        _check_promotion(
            settings=settings,
            ml_auc_pr=0.70,
            ml_brier=0.10,
            baseline_auc_pr=0.55,
            hit_rate=0.85,
            far=0.50,  # FAR too high
            lead_time_hours=24.0,
        )
        is False
    )


def test_promotion_gate_passes(settings) -> None:  # type: ignore[no-untyped-def]
    assert (
        _check_promotion(
            settings=settings,
            ml_auc_pr=0.70,
            ml_brier=0.10,
            baseline_auc_pr=0.55,
            hit_rate=0.85,
            far=0.20,
            lead_time_hours=24.0,
        )
        is True
    )


def test_need_minimum_samples_too_few() -> None:
    assert _need_minimum_samples([]) is True


def test_need_minimum_samples_single_class() -> None:
    from datetime import UTC, datetime

    from limen.data.repos.training_samples_repo import TrainingSample

    samples = [
        TrainingSample(
            cell_id=f"c-{i}",
            valuation_time=datetime(2026, 1, 1, tzinfo=UTC),
            label=1,  # all positives → useless
            label_source="iffi",
            features={},
            split_block="b-0",
        )
        for i in range(50)
    ]
    assert _need_minimum_samples(samples) is True


@pytest.mark.asyncio
async def test_run_training_skips_on_empty_dataset(settings) -> None:  # type: ignore[no-untyped-def]
    """No samples → early exit with a benign zero result."""
    # Force fetch_samples → empty by patching the repo.
    import limen.ml.train as train_mod

    async def _empty() -> list:  # type: ignore[type-arg]
        return []

    train_mod.fetch_samples = _empty  # type: ignore[assignment]
    result: TrainResult = await run_training(settings=settings)
    assert result.run_id is None
    assert result.promoted is False
    assert result.auc_pr_mean == 0.0
