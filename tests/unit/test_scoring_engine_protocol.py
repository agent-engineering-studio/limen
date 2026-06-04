"""V2 — scoring-engine Protocol + resolver behaviour."""

from __future__ import annotations

from datetime import UTC, datetime

from limen.config.settings import (
    ScoringEngineKind,
    ScoringMode,
    ScoringSettings,
    Settings,
)
from limen.core.models.risk import (
    CellFeatureBundle,
    DynamicInputs,
    RainfallSeries,
    StaticFactors,
)
from limen.core.scoring.base import ScoringEngine
from limen.core.scoring.engine import MultiFactorScoringEngine
from limen.core.scoring.resolver import resolve_challenger, resolve_scoring_engine


def _bundle() -> CellFeatureBundle:
    return CellFeatureBundle(
        aoi_id="aoi",
        cell_id="c",
        static=StaticFactors(cell_id="c", susc_ispra=0.5),
        dynamic=DynamicInputs(
            valuation_time=datetime(2026, 1, 1, tzinfo=UTC), rainfall=RainfallSeries()
        ),
    )


def test_deterministic_engine_satisfies_protocol() -> None:
    engine = MultiFactorScoringEngine()
    assert isinstance(engine, ScoringEngine)


def test_resolver_defaults_to_deterministic() -> None:
    s = Settings.model_validate({})
    engine = resolve_scoring_engine(settings=s)
    assert isinstance(engine, MultiFactorScoringEngine)
    # Returned engine MUST satisfy the structural Protocol.
    assert isinstance(engine, ScoringEngine)
    assert engine.score(_bundle()).score >= 0.0


def test_resolver_falls_back_when_ml_unavailable() -> None:
    """No registered MLflow model → resolver returns the V1 engine."""
    s = Settings.model_validate(
        {
            "scoring": ScoringSettings(
                engine=ScoringEngineKind.ML,
                mlflow_tracking_uri="file:///tmp/limen-missing-mlflow",
            ).model_dump(),
        }
    )
    engine = resolve_scoring_engine(settings=s)
    # Fallback path: still a deterministic engine.
    assert isinstance(engine, MultiFactorScoringEngine)


def test_challenger_is_none_in_champion_only_mode() -> None:
    s = Settings.model_validate({"scoring": ScoringSettings().model_dump()})
    assert resolve_challenger(settings=s) is None


def test_challenger_is_v1_when_champion_is_ml_in_shadow() -> None:
    s = Settings.model_validate(
        {
            "scoring": ScoringSettings(
                engine=ScoringEngineKind.ML,
                mode=ScoringMode.SHADOW,
            ).model_dump(),
        }
    )
    challenger = resolve_challenger(settings=s)
    # ML champion + shadow → challenger = V1 deterministic
    assert isinstance(challenger, MultiFactorScoringEngine)
