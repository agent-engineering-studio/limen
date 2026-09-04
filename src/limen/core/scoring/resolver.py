"""Engine resolver — picks an engine for a hazard and degrades to V1.

Thin layer over :mod:`limen.core.scoring.registry`. The registry answers
"which engine is registered for this hazard and implementation"; the resolver
adds the two operational policies that must not live in a lookup table:

* **``SCORING__ENGINE`` selects the implementation**, defaulting to the
  deterministic V1 engine.
* **A V2 failure falls back to the V1 baseline of the same hazard, logs why,
  and never raises.** The project doc requires the deterministic baseline to
  stay live, so a missing MLflow model or an uninstalled ``ml`` group degrades
  the sweep instead of stopping it.

The fallback is *within one hazard*. A hazard with no deterministic engine, or
with no YAML, is a misconfiguration and raises: scoring flood with landslide
thresholds would be wrong numbers presented as right, which is worse than a
loud failure. ``check_scorable`` surfaces that at startup instead of mid-sweep.

Fase 1 champion resolution is landslide-only by construction: the workflow is
parameterised by hazard in #85, and until then a non-default hazard reaching
here is a bug, not a configuration choice.

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
from limen.core.scoring.registry import EngineNotRegisteredError, is_registered, resolve

_log: structlog.stdlib.BoundLogger = get_logger(__name__)


class HazardNotScorableError(RuntimeError):
    """An enabled hazard has no engine, or no thresholds file.

    A misconfiguration, not an operational hiccup: it cannot be degraded
    around, because there is no correct number to produce.
    """


def _deterministic(
    hazard: HazardType, thresholds: RegionalThresholds | None
) -> ScoringEngine[ComponentBreakdown]:
    """The V1 baseline for ``hazard``.

    Raises :class:`HazardNotScorableError` when the hazard has no YAML. It
    must NOT silently fall back to the landslide file: that would score a
    flood cell with slope-failure thresholds.
    """
    from limen.core.scoring.engine import MultiFactorScoringEngine
    from limen.core.scoring.regional_thresholds import load_hazard_thresholds

    if thresholds is not None:
        return MultiFactorScoringEngine(thresholds)
    try:
        return MultiFactorScoringEngine(load_hazard_thresholds(hazard))
    except FileNotFoundError as exc:
        raise HazardNotScorableError(
            f"hazard {hazard.value!r} has no thresholds file "
            f"(expected config/hazards/{hazard.value}.yaml)"
        ) from exc


def check_scorable(hazard: HazardType, kind: ScoringEngineKind) -> None:
    """Raise unless ``hazard`` can actually be scored.

    Called at startup for every entry of ``HAZARDS__ENABLED`` so a typo or a
    half-finished hazard shows up there, not as an ``AttributeError`` in the
    middle of the hourly sweep.
    """
    from limen.core.scoring.regional_thresholds import hazard_thresholds_path

    if not is_registered(hazard, ScoringEngineKind.DETERMINISTIC):
        raise HazardNotScorableError(
            f"hazard {hazard.value!r} has no deterministic engine registered"
        )
    if not is_registered(hazard, kind):
        raise HazardNotScorableError(
            f"hazard {hazard.value!r} has no {kind.value!r} engine registered"
        )
    if not hazard_thresholds_path(hazard).exists():
        raise HazardNotScorableError(
            f"hazard {hazard.value!r} has no thresholds file "
            f"(expected config/hazards/{hazard.value}.yaml)"
        )


def _require_landslide(hazard: HazardType) -> None:
    """Fase 1 resolves champions for the default hazard only.

    The cast below narrows the registry's base breakdown to the landslide one,
    and that narrowing is only sound while this holds. A flood engine resolved
    through here would fail as an ``AttributeError`` on ``.static_terms``
    inside ``RiskScoringExecutor``, mid-sweep. #85 parameterises the workflow
    and lifts this.
    """
    if hazard is not DEFAULT_HAZARD:
        raise HazardNotScorableError(
            f"champion resolution is {DEFAULT_HAZARD.value}-only until the workflow "
            f"is parameterised per hazard (#85); got {hazard.value!r}"
        )


def _try_registry(
    hazard: HazardType,
    kind: ScoringEngineKind,
    thresholds: RegionalThresholds | None,
    *,
    event: str,
    settings: Settings | None = None,
) -> ScoringEngine[ComponentBreakdown] | None:
    """Build from the registry, or log and return ``None``.

    Every failure mode collapses here on purpose: an unregistered pair, an
    optional dependency that is not installed, an MLflow registry with no
    promoted model. The caller decides what to do without a raise, because
    engine resolution runs inside the hourly sweep.
    """
    try:
        engine = resolve(hazard, kind, settings=settings, thresholds=thresholds)
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
    _require_landslide(hazard)

    if kind is ScoringEngineKind.DETERMINISTIC:
        engine = _try_registry(
            hazard,
            kind,
            thresholds,
            event="scoring.deterministic_unavailable",
            settings=s,
        )
        if engine is not None:
            _log.info("scoring.resolved", hazard=hazard.value, engine=kind.value)
            return engine
        # A missing deterministic registration is a programming error, not an
        # operational one, but the sweep still has to produce numbers.
        return _deterministic(hazard, thresholds)

    engine = _try_registry(
        hazard, kind, thresholds, event="scoring.ml_load_failed_fallback", settings=s
    )
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
    _require_landslide(hazard)
    # In shadow mode the challenger is the OTHER implementation: champion
    # deterministic ⇒ challenger ML, and vice-versa.
    other = (
        ScoringEngineKind.ML
        if s.scoring.engine is ScoringEngineKind.DETERMINISTIC
        else ScoringEngineKind.DETERMINISTIC
    )
    return _try_registry(
        hazard, other, thresholds, event="scoring.challenger_load_failed", settings=s
    )


__all__ = [
    "HazardNotScorableError",
    "check_scorable",
    "resolve_challenger",
    "resolve_scoring_engine",
]
