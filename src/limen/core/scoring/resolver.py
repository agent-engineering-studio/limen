"""Engine resolver — picks an engine for a hazard and degrades to V1.

Thin layer over :mod:`limen.core.scoring.registry`. The registry answers
"which engine is registered for this hazard and implementation"; the resolver
adds the two operational policies that must not live in a lookup table:

* **``SCORING__ENGINE`` selects the implementation**, defaulting to the
  deterministic V1 engine.
* **A V2 failure falls back to V1 and logs why, never raises.** The project
  doc requires the deterministic baseline to stay a live fallback, so a
  missing MLflow model or an uninstalled ``ml`` group degrades the sweep
  instead of stopping it.

The public API is unchanged from before the registry existed, so the workflow
and ``AppDependencies`` did not have to move.
"""

from __future__ import annotations

from typing import cast

import structlog

from limen.config.settings import ScoringEngineKind, ScoringMode, Settings, get_settings
from limen.core.logging import get_logger
from limen.core.models.hazard import DEFAULT_HAZARD, HazardType
from limen.core.models.risk import ComponentBreakdown
from limen.core.scoring.base import ScoringEngine
from limen.core.scoring.regional_thresholds import RegionalThresholds
from limen.core.scoring.registry import EngineNotRegisteredError, resolve

_log: structlog.stdlib.BoundLogger = get_logger(__name__)


def _deterministic(
    hazard: HazardType, thresholds: RegionalThresholds | None
) -> ScoringEngine[ComponentBreakdown]:
    """The V1 baseline for ``hazard``, which must always be resolvable."""
    from limen.core.scoring.engine import MultiFactorScoringEngine
    from limen.core.scoring.regional_thresholds import load_hazard_thresholds

    return MultiFactorScoringEngine(thresholds or load_hazard_thresholds(hazard))


def _try_registry(
    hazard: HazardType,
    kind: ScoringEngineKind,
    thresholds: RegionalThresholds | None,
    *,
    event: str,
) -> ScoringEngine[ComponentBreakdown] | None:
    """Build from the registry, or log and return ``None``.

    Every failure mode collapses here on purpose: an unregistered pair, an
    optional dependency that is not installed, an MLflow registry with no
    promoted model. The caller decides what to do without a raise, because
    engine resolution runs inside the hourly sweep.
    """
    try:
        engine = resolve(hazard, kind, thresholds=thresholds)
    except EngineNotRegisteredError as exc:
        _log.warning(event, hazard=hazard.value, kind=kind.value, error=str(exc))
        return None
    except Exception as exc:
        _log.warning(
            event,
            hazard=hazard.value,
            kind=kind.value,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return None
    # A heterogeneous registry cannot express "this hazard's engine yields
    # this hazard's breakdown" in the type system: it is typed on the base so
    # it can hold engines for several hazards. The narrowing is guaranteed by
    # the registration, and Fase 2 will move it into a per-hazard resolver.
    return cast("ScoringEngine[ComponentBreakdown]", engine)


def resolve_scoring_engine(
    *,
    settings: Settings | None = None,
    thresholds: RegionalThresholds | None = None,
    hazard: HazardType = DEFAULT_HAZARD,
) -> ScoringEngine[ComponentBreakdown]:
    """Return the champion engine for ``hazard``.

    Falls back to the deterministic engine on any V2 problem and logs the
    reason — never raises during resolution.
    """
    s = settings or get_settings()
    kind = s.scoring.engine

    if kind is ScoringEngineKind.DETERMINISTIC:
        engine = _try_registry(hazard, kind, thresholds, event="scoring.deterministic_unavailable")
        if engine is not None:
            _log.info("scoring.resolved", hazard=hazard.value, engine=kind.value)
            return engine
        # A missing deterministic registration is a programming error, not an
        # operational one, but the sweep still has to produce numbers.
        return _deterministic(hazard, thresholds)

    engine = _try_registry(hazard, kind, thresholds, event="scoring.ml_load_failed_fallback")
    if engine is None:
        _log.info("scoring.resolved", hazard=hazard.value, engine="deterministic-fallback")
        return _deterministic(hazard, thresholds)
    _log.info("scoring.resolved", hazard=hazard.value, engine=kind.value)
    return engine


def resolve_challenger(
    *,
    settings: Settings | None = None,
    thresholds: RegionalThresholds | None = None,
    hazard: HazardType = DEFAULT_HAZARD,
) -> ScoringEngine[ComponentBreakdown] | None:
    """Return the shadow challenger for ``hazard``, if shadow mode is active.

    The champion stays the authoritative engine; the challenger only
    computes-and-logs in parallel. ``None`` outside shadow mode, or when the
    challenger cannot be built.
    """
    s = settings or get_settings()
    if s.scoring.mode is not ScoringMode.SHADOW:
        return None
    # In shadow mode the challenger is the OTHER implementation: champion
    # deterministic ⇒ challenger ML, and vice-versa.
    other = (
        ScoringEngineKind.ML
        if s.scoring.engine is ScoringEngineKind.DETERMINISTIC
        else ScoringEngineKind.DETERMINISTIC
    )
    return _try_registry(hazard, other, thresholds, event="scoring.challenger_load_failed")


__all__ = ["resolve_challenger", "resolve_scoring_engine"]
