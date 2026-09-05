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

Champion resolution is hazard-generic from Fase 2: the record the workflow
builds carries the hazard's own breakdown, so the resolver no longer has to
refuse an engine whose components it cannot name.

The public API is unchanged from before the registry existed, so the workflow
and ``AppDependencies`` did not have to move.
"""

from __future__ import annotations

import structlog

from limen.config.settings import ScoringEngineKind, ScoringMode, Settings, get_settings
from limen.core.logging import get_logger
from limen.core.models.hazard import DEFAULT_HAZARD, HazardType
from limen.core.models.risk import HazardBreakdown
from limen.core.scoring.base import ScoringEngine
from limen.core.scoring.regional_thresholds import RegionalThresholds
from limen.core.scoring.registry import (
    EngineNotRegisteredError,
    is_registered,
    resolve,
)

_log: structlog.stdlib.BoundLogger = get_logger(__name__)


class HazardNotScorableError(RuntimeError):
    """An enabled hazard has no engine, or no thresholds file.

    A misconfiguration, not an operational hiccup: it cannot be degraded
    around, because there is no correct number to produce.
    """


def _deterministic(
    hazard: HazardType, thresholds: RegionalThresholds | None
) -> ScoringEngine[HazardBreakdown]:
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
        loaded = load_hazard_thresholds(hazard)
    except FileNotFoundError as exc:
        raise HazardNotScorableError(
            f"hazard {hazard.value!r} has no thresholds file "
            f"(expected config/hazards/{hazard.value}.yaml)"
        ) from exc
    if not isinstance(loaded, RegionalThresholds):
        # Reached only for a hazard with its own schema but no registered
        # engine. Building the landslide formula on its config is not a
        # degradation, it is a wrong answer, so it is refused.
        raise HazardNotScorableError(
            f"hazard {hazard.value!r} has no deterministic engine registered, and its "
            f"configuration ({type(loaded).__name__}) is not the landslide baseline's"
        )
    return MultiFactorScoringEngine(loaded)


def check_scorable(hazard: HazardType) -> None:
    """Raise unless ``hazard`` can actually be scored.

    Called at startup for every enabled hazard so a typo or a half-finished
    one shows up there, not as a ``FileNotFoundError`` in the middle of the
    hourly sweep.

    It takes no implementation: the resolver degrades to the deterministic
    baseline whenever the configured one is missing or fails, so a hazard
    that scores fine with V1 must not be refused because its ML challenger
    is absent.
    """
    from limen.core.scoring.regional_thresholds import hazard_thresholds_path

    # The deterministic engine is the only hard requirement: the resolver
    # degrades to it whenever the configured implementation is missing or
    # fails, so demanding `kind` here would refuse a hazard that would in fact
    # score perfectly well with V1.
    if not is_registered(hazard, ScoringEngineKind.DETERMINISTIC):
        raise HazardNotScorableError(
            f"hazard {hazard.value!r} has no deterministic engine registered"
        )
    if not hazard_thresholds_path(hazard).exists():
        raise HazardNotScorableError(
            f"hazard {hazard.value!r} has no thresholds file "
            f"(expected config/hazards/{hazard.value}.yaml)"
        )
    # No breakdown-shape check any more: `CellRiskRecord` carries whatever
    # the engine produced, and every consumer reads it through the
    # projections on `HazardBreakdown`. What remains fatal is having no
    # engine or no configuration, which is checked above.


def _try_registry(
    hazard: HazardType,
    kind: ScoringEngineKind,
    thresholds: RegionalThresholds | None,
    *,
    event: str,
    settings: Settings | None = None,
) -> ScoringEngine[HazardBreakdown] | None:
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
    return engine


def _deterministic_champion(
    hazard: HazardType,
    thresholds: RegionalThresholds | None,
    settings: Settings | None,
) -> ScoringEngine[HazardBreakdown]:
    """The V1 baseline for ``hazard``, preferring its registered engine.

    Going through the registry matters: a hazard with its own deterministic
    engine must get *that* one, not the generic landslide formula. The direct
    construction is the last resort, for a hazard whose registration is
    missing entirely.
    """
    engine = _try_registry(
        hazard,
        ScoringEngineKind.DETERMINISTIC,
        thresholds,
        event="scoring.deterministic_unavailable",
        settings=settings,
    )
    if engine is not None:
        return engine
    return _deterministic(hazard, thresholds)


def resolve_scoring_engine(
    *,
    settings: Settings | None = None,
    thresholds: RegionalThresholds | None = None,
    hazard: HazardType = DEFAULT_HAZARD,
) -> ScoringEngine[HazardBreakdown]:
    """Return the champion engine for ``hazard``.

    Falls back to that hazard's deterministic engine on any V2 problem and
    logs the reason.
    """
    s = settings or get_settings()
    kind = s.scoring.engine

    if kind is ScoringEngineKind.DETERMINISTIC:
        engine = _deterministic_champion(hazard, thresholds, s)
        _log.info("scoring.resolved", hazard=hazard.value, engine=kind.value)
        return engine

    engine_or_none = _try_registry(
        hazard, kind, thresholds, event="scoring.ml_load_failed_fallback", settings=s
    )
    if engine_or_none is None:
        _log.info("scoring.resolved", hazard=hazard.value, engine="deterministic-fallback")
        return _deterministic_champion(hazard, thresholds, s)
    _log.info("scoring.resolved", hazard=hazard.value, engine=kind.value)
    return engine_or_none


def resolve_challenger(
    *,
    settings: Settings | None = None,
    thresholds: RegionalThresholds | None = None,
    hazard: HazardType = DEFAULT_HAZARD,
) -> ScoringEngine[HazardBreakdown] | None:
    """Return the shadow challenger for ``hazard``, if shadow mode is active.

    The champion stays the authoritative engine; the challenger only
    computes-and-logs in parallel. ``None`` outside shadow mode, or when the
    challenger cannot be built.

    Typed on the **base** breakdown, unlike the champion: the shadow executor
    serialises whatever it gets, so it needs no named component and imposes no
    compatibility requirement.
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
    return _try_registry(
        hazard, other, thresholds, event="scoring.challenger_load_failed", settings=s
    )


__all__ = [
    "HazardNotScorableError",
    "check_scorable",
    "resolve_challenger",
    "resolve_scoring_engine",
]
