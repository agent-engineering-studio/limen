"""Engine registry, indexed by hazard **and** implementation.

Two orthogonal axes, not one. The hazard says *what danger* is being scored
(landslide, flood, wildfire); the implementation says *how* (the deterministic
V1 engine or a V2 ML challenger). A registry keyed only on hazard would have
nowhere to put the ML challenger for wildfire in Fase 2, and one keyed only on
implementation is what the codebase already had.

Registering an engine is the *only* production change a new hazard needs
besides its YAML: the workflow, the API and the persistence layer all speak
through :class:`HazardScoringEngine`. That is the acceptance criterion of
issue #57, and a test in ``tests/unit/test_scoring_registry.py`` holds it.

Engines are built lazily through factories. The ML engine talks to an MLflow
registry at construction time, so importing this module must never trigger
that; ``resolve`` is where the cost is paid, and where a failure degrades to
the V1 baseline.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from limen.config.settings import ScoringEngineKind, Settings
from limen.core.logging import get_logger
from limen.core.models.hazard import HazardType
from limen.core.models.risk import ComponentBreakdown, HazardBreakdown
from limen.core.scoring.base import ScoringEngine
from limen.core.scoring.regional_thresholds import RegionalThresholds

log = get_logger(__name__)

#: The name issue #57 asks for. Covariant in the breakdown, so an engine
#: registered for one hazard is usable wherever the base breakdown is enough.
HazardScoringEngine = ScoringEngine[HazardBreakdown]

#: A factory takes the two things a caller may inject: the settings and a
#: thresholds override, each optional. `AppDependencies` and the tests supply
#: a config without writing it to disk, and the ML engine reads its MLflow
#: coordinates from the settings -- reaching for the global ones inside a
#: factory would silently discard an injected config, which is how a test
#: pointed at a missing registry ends up passing for the wrong reason.
EngineFactory = Callable[["Settings | None", "RegionalThresholds | None"], HazardScoringEngine]


@dataclass(frozen=True, slots=True)
class _Entry:
    factory: EngineFactory
    #: The breakdown class the engine produces. Declared at registration
    #: because it cannot be discovered without scoring a cell, and a consumer
    #: that reads specific components has to know before the sweep starts
    #: whether they will be there.
    breakdown: type[HazardBreakdown]


_REGISTRY: dict[tuple[HazardType, ScoringEngineKind], _Entry] = {}


class EngineNotRegisteredError(LookupError):
    """No engine is registered for a (hazard, implementation) pair."""


def register(
    hazard: HazardType,
    kind: ScoringEngineKind,
    factory: EngineFactory,
    *,
    breakdown: type[HazardBreakdown],
    replace: bool = False,
) -> None:
    """Register ``factory`` as the engine for ``(hazard, kind)``.

    ``breakdown`` declares which breakdown class the engine produces. It is
    required because nothing can infer it without scoring a cell, and a
    consumer that reads named components -- ``RiskScoringExecutor`` reads
    ``.s``, ``.static_terms`` and the rest -- must be able to refuse an
    incompatible engine at build time instead of dying on an
    ``AttributeError`` halfway through the hourly sweep.

    Registering the same pair twice is refused unless ``replace`` is set: a
    silent overwrite would make the champion depend on module import order.
    """
    key = (hazard, kind)
    if key in _REGISTRY and not replace:
        raise ValueError(
            f"engine already registered for {hazard.value}/{kind.value}; "
            "pass replace=True to override it deliberately"
        )
    _REGISTRY[key] = _Entry(factory=factory, breakdown=breakdown)


def unregister(hazard: HazardType, kind: ScoringEngineKind) -> None:
    """Drop a registration. Exists for tests; harmless if absent."""
    _REGISTRY.pop((hazard, kind), None)


def resolve(
    hazard: HazardType,
    kind: ScoringEngineKind,
    *,
    settings: Settings | None = None,
    thresholds: RegionalThresholds | None = None,
) -> HazardScoringEngine:
    """Build the engine registered for ``(hazard, kind)``.

    Raises :class:`EngineNotRegisteredError` when the pair is unknown, naming
    what *is* available: a mistyped hazard in a config should fail loudly at
    startup, not silently score nothing.
    """
    try:
        entry = _REGISTRY[(hazard, kind)]
    except KeyError:
        available = ", ".join(sorted(f"{h.value}/{k.value}" for h, k in _REGISTRY))
        raise EngineNotRegisteredError(
            f"no scoring engine for {hazard.value}/{kind.value}; registered: {available}"
        ) from None
    return entry.factory(settings, thresholds)


def is_registered(hazard: HazardType, kind: ScoringEngineKind) -> bool:
    return (hazard, kind) in _REGISTRY


def registered_breakdown(hazard: HazardType, kind: ScoringEngineKind) -> type[HazardBreakdown]:
    """The breakdown class the registered engine produces.

    Lets a caller check compatibility *before* building the engine, which is
    the whole point of declaring it at registration.
    """
    try:
        return _REGISTRY[(hazard, kind)].breakdown
    except KeyError:
        raise EngineNotRegisteredError(
            f"no scoring engine for {hazard.value}/{kind.value}"
        ) from None


def registered_hazards() -> frozenset[HazardType]:
    """Hazards with at least one engine."""
    return frozenset(hazard for hazard, _ in _REGISTRY)


def registered_pairs() -> frozenset[tuple[HazardType, ScoringEngineKind]]:
    return frozenset(_REGISTRY)


# ---------------------------------------------------------------------------
# Built-in registrations
# ---------------------------------------------------------------------------
def _landslide_deterministic(
    settings: Settings | None = None,  # noqa: ARG001 — part of the EngineFactory shape
    thresholds: RegionalThresholds | None = None,
) -> HazardScoringEngine:
    from limen.core.scoring.engine import MultiFactorScoringEngine
    from limen.core.scoring.regional_thresholds import load_hazard_thresholds

    return MultiFactorScoringEngine(thresholds or load_hazard_thresholds(HazardType.LANDSLIDE))


def _landslide_ml(
    settings: Settings | None = None,
    thresholds: RegionalThresholds | None = None,
) -> HazardScoringEngine:
    # Imported inside the factory: the `ml` dependency group is optional and
    # `from_registry` reaches out to MLflow, so neither cost belongs at import
    # time. A failure here is caught by the resolver, which falls back to V1.
    from limen.config.settings import get_settings
    from limen.core.scoring.ml_engine import MLScoringEngine
    from limen.core.scoring.regional_thresholds import load_hazard_thresholds

    s = settings or get_settings()
    return MLScoringEngine.from_registry(
        tracking_uri=s.scoring.mlflow_tracking_uri,
        registered_model=s.scoring.mlflow_registered_model,
        stage=s.scoring.mlflow_model_stage,
        thresholds=thresholds or load_hazard_thresholds(HazardType.LANDSLIDE),
    )


register(
    HazardType.LANDSLIDE,
    ScoringEngineKind.DETERMINISTIC,
    _landslide_deterministic,
    breakdown=ComponentBreakdown,
)
register(
    HazardType.LANDSLIDE,
    ScoringEngineKind.ML,
    _landslide_ml,
    breakdown=ComponentBreakdown,
)


__all__ = [
    "EngineFactory",
    "EngineNotRegisteredError",
    "HazardScoringEngine",
    "is_registered",
    "register",
    "registered_breakdown",
    "registered_hazards",
    "registered_pairs",
    "resolve",
    "unregister",
]
