"""Engine resolver — :data:`SCORING__ENGINE` selects V1 or V2.

Default is the deterministic V1 engine. ``ml`` flips to the V2
:class:`MLScoringEngine` (drop-in, same interface). Falling back to V1
on V2 load failure is intentional — the project doc requires the V1
baseline to remain a live fallback.
"""

from __future__ import annotations

import structlog

from limen.config.settings import ScoringEngineKind, Settings, get_settings
from limen.core.logging import get_logger
from limen.core.scoring.base import ScoringEngine
from limen.core.scoring.engine import MultiFactorScoringEngine
from limen.core.scoring.regional_thresholds import (
    RegionalThresholds,
    load_regional_thresholds,
)

_log: structlog.stdlib.BoundLogger = get_logger(__name__)


def resolve_scoring_engine(
    *,
    settings: Settings | None = None,
    thresholds: RegionalThresholds | None = None,
) -> ScoringEngine:
    """Return the engine selected by ``settings.scoring.engine``.

    Falls back to the deterministic engine on V2 load errors and logs
    the reason — never raises during resolution.
    """
    s = settings or get_settings()
    th = thresholds or load_regional_thresholds()
    deterministic = MultiFactorScoringEngine(th)

    if s.scoring.engine is ScoringEngineKind.DETERMINISTIC:
        _log.info("scoring.resolved", engine="deterministic")
        return deterministic

    try:
        from limen.core.scoring.ml_engine import MLScoringEngine
    except Exception as exc:
        _log.warning(
            "scoring.ml_unavailable_fallback",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return deterministic

    try:
        ml = MLScoringEngine.from_registry(
            tracking_uri=s.scoring.mlflow_tracking_uri,
            registered_model=s.scoring.mlflow_registered_model,
            stage=s.scoring.mlflow_model_stage,
            thresholds=th,
        )
    except Exception as exc:
        _log.warning(
            "scoring.ml_load_failed_fallback",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return deterministic

    _log.info("scoring.resolved", engine="ml")
    return ml


def resolve_challenger(
    *,
    settings: Settings | None = None,
    thresholds: RegionalThresholds | None = None,
) -> ScoringEngine | None:
    """Return the shadow challenger, if shadow mode is active.

    The champion (returned by :func:`resolve_scoring_engine`) stays the
    authoritative engine; the challenger only computes-and-logs in
    parallel. Returns ``None`` outside shadow mode or when the
    challenger can't be loaded.
    """
    from limen.config.settings import ScoringMode

    s = settings or get_settings()
    if s.scoring.mode is not ScoringMode.SHADOW:
        return None
    # In shadow mode the challenger is the OTHER engine — if the champion
    # is deterministic, the challenger is ML, and vice-versa.
    th = thresholds or load_regional_thresholds()
    if s.scoring.engine is ScoringEngineKind.DETERMINISTIC:
        try:
            from limen.core.scoring.ml_engine import MLScoringEngine
        except Exception as exc:
            _log.warning("scoring.challenger_unavailable", error=str(exc))
            return None
        try:
            return MLScoringEngine.from_registry(
                tracking_uri=s.scoring.mlflow_tracking_uri,
                registered_model=s.scoring.mlflow_registered_model,
                stage=s.scoring.mlflow_model_stage,
                thresholds=th,
            )
        except Exception as exc:
            _log.warning("scoring.challenger_load_failed", error=str(exc))
            return None
    # Champion is ML → V1 deterministic is the natural challenger.
    return MultiFactorScoringEngine(th)


__all__ = ["resolve_challenger", "resolve_scoring_engine"]
