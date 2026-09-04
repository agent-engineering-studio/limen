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

from limen.config.settings import ScoringEngineKind
from limen.core.logging import get_logger
from limen.core.models.hazard import HazardType
from limen.core.models.risk import HazardBreakdown
from limen.core.scoring.base import ScoringEngine
from limen.core.scoring.regional_thresholds import RegionalThresholds

log = get_logger(__name__)

#: The name issue #57 asks for. Covariant in the breakdown, so an engine
#: registered for one hazard is usable wherever the base breakdown is enough.
HazardScoringEngine = ScoringEngine[HazardBreakdown]

#: A factory takes one optional argument: a thresholds override. Everything
#: else an engine needs comes from its hazard's YAML and the settings. The
#: override exists because `AppDependencies` and the tests inject a config
#: without writing it to disk; passing ``None`` means "load the hazard's own".
EngineFactory = Callable[["RegionalThresholds | None"], HazardScoringEngine]

_REGISTRY: dict[tuple[HazardType, ScoringEngineKind], EngineFactory] = {}


class EngineNotRegisteredError(LookupError):
    """No engine is registered for a (hazard, implementation) pair."""


def register(
    hazard: HazardType,
    kind: ScoringEngineKind,
    factory: EngineFactory,
    *,
    replace: bool = False,
) -> None:
    """Register ``factory`` as the engine for ``(hazard, kind)``.

    Registering the same pair twice is refused unless ``replace`` is set: a
    silent overwrite would make the champion depend on module import order.
    """
    key = (hazard, kind)
    if key in _REGISTRY and not replace:
        raise ValueError(
            f"engine already registered for {hazard.value}/{kind.value}; "
            "pass replace=True to override it deliberately"
        )
    _REGISTRY[key] = factory


def unregister(hazard: HazardType, kind: ScoringEngineKind) -> None:
    """Drop a registration. Exists for tests; harmless if absent."""
    _REGISTRY.pop((hazard, kind), None)


def resolve(
    hazard: HazardType,
    kind: ScoringEngineKind,
    *,
    thresholds: RegionalThresholds | None = None,
) -> HazardScoringEngine:
    """Build the engine registered for ``(hazard, kind)``.

    Raises :class:`EngineNotRegisteredError` when the pair is unknown, naming
    what *is* available: a mistyped hazard in a config should fail loudly at
    startup, not silently score nothing.
    """
    try:
        factory = _REGISTRY[(hazard, kind)]
    except KeyError:
        available = ", ".join(sorted(f"{h.value}/{k.value}" for h, k in _REGISTRY))
        raise EngineNotRegisteredError(
            f"no scoring engine for {hazard.value}/{kind.value}; registered: {available}"
        ) from None
    return factory(thresholds)


def is_registered(hazard: HazardType, kind: ScoringEngineKind) -> bool:
    return (hazard, kind) in _REGISTRY


def registered_hazards() -> frozenset[HazardType]:
    """Hazards with at least one engine."""
    return frozenset(hazard for hazard, _ in _REGISTRY)


def registered_pairs() -> frozenset[tuple[HazardType, ScoringEngineKind]]:
    return frozenset(_REGISTRY)


# ---------------------------------------------------------------------------
# Built-in registrations
# ---------------------------------------------------------------------------
def _landslide_deterministic(
    thresholds: RegionalThresholds | None = None,
) -> HazardScoringEngine:
    from limen.core.scoring.engine import MultiFactorScoringEngine
    from limen.core.scoring.regional_thresholds import load_hazard_thresholds

    return MultiFactorScoringEngine(thresholds or load_hazard_thresholds(HazardType.LANDSLIDE))


def _landslide_ml(thresholds: RegionalThresholds | None = None) -> HazardScoringEngine:
    # Imported inside the factory: the `ml` dependency group is optional and
    # `from_registry` reaches out to MLflow, so neither cost belongs at import
    # time. A failure here is caught by the resolver, which falls back to V1.
    from limen.config.settings import get_settings
    from limen.core.scoring.ml_engine import MLScoringEngine
    from limen.core.scoring.regional_thresholds import load_hazard_thresholds

    s = get_settings()
    return MLScoringEngine.from_registry(
        tracking_uri=s.scoring.mlflow_tracking_uri,
        registered_model=s.scoring.mlflow_registered_model,
        stage=s.scoring.mlflow_model_stage,
        thresholds=thresholds or load_hazard_thresholds(HazardType.LANDSLIDE),
    )


register(HazardType.LANDSLIDE, ScoringEngineKind.DETERMINISTIC, _landslide_deterministic)
register(HazardType.LANDSLIDE, ScoringEngineKind.ML, _landslide_ml)


__all__ = [
    "EngineFactory",
    "EngineNotRegisteredError",
    "HazardScoringEngine",
    "is_registered",
    "register",
    "registered_hazards",
    "registered_pairs",
    "resolve",
    "unregister",
]
