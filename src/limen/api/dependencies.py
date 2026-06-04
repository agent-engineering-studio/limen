"""Dependency container + FastAPI ``Depends`` providers.

The container is built once at lifespan start and lives as
``app.state.deps``. Route handlers receive it via the
:data:`DepsDep` annotated alias instead of reading globals.

Keeping every dependency in a single dataclass makes the test wiring
explicit: tests construct a :class:`AppDependencies` with a stub LLM
factory + a per-test pool and hand it to :func:`build_app_with_deps`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, Request

from limen.agents.grounding.service import GroundingService
from limen.agents.llm_factory.base import LlmClientFactory
from limen.config.settings import Settings, get_settings
from limen.core.scoring.base import ScoringEngine
from limen.core.scoring.engine import MultiFactorScoringEngine
from limen.core.scoring.regional_thresholds import (
    RegionalThresholds,
    load_regional_thresholds,
)
from limen.core.scoring.resolver import resolve_challenger, resolve_scoring_engine
from limen.data.caching.postgres_cache import DistributedCache, PostgresCache
from limen.data.object_store import ObjectStore, build_object_store
from limen.notifications.dispatcher import (
    NotificationDispatcher,
    build_default_dispatcher,
)

if TYPE_CHECKING:
    import asyncpg

    from limen.agents.workflow_runtime.builder import Workflow


@dataclass(slots=True)
class AppDependencies:
    """Process-wide DI container; built once in the lifespan."""

    settings: Settings
    pool: asyncpg.Pool
    cache: DistributedCache
    object_store: ObjectStore
    llm_factory: LlmClientFactory
    thresholds: RegionalThresholds
    engine: MultiFactorScoringEngine
    notification_dispatcher: NotificationDispatcher
    # V2 — the resolved engine (V1 by default, V2 when promoted) + the
    # shadow challenger. The workflow injects both into its scoring
    # executors via the settings-driven resolver.
    scoring_engine: ScoringEngine | None = None
    challenger_engine: ScoringEngine | None = None
    # V2.x — KG grounding service, only constructed when `kg.enabled` is true.
    grounding_service: GroundingService | None = None

    @classmethod
    async def build(
        cls,
        *,
        pool: asyncpg.Pool,
        settings: Settings | None = None,
        llm_factory: LlmClientFactory | None = None,
        notification_dispatcher: NotificationDispatcher | None = None,
    ) -> AppDependencies:
        """Construct the container around an already-initialised pool.

        ``llm_factory`` defaults to the env-resolved factory; tests pass
        :class:`StubLlmClientFactory` instead. ``notification_dispatcher``
        defaults to one wired from :class:`NotificationsSettings`; tests
        pass a stub dispatcher with no real channels.
        """
        # Late imports keep `import limen.api.dependencies` cheap and
        # avoid pulling the agents subsystem unless we're actually
        # wiring the API.
        from limen.agents.llm_factory.resolver import resolve_llm_factory

        s = settings or get_settings()
        factory = llm_factory or resolve_llm_factory(s)
        thresholds = load_regional_thresholds()
        dispatcher = notification_dispatcher or build_default_dispatcher(s.notifications)
        # The resolver returns the V1 engine on any failure — the V2 ML
        # engine is opt-in via SCORING__ENGINE=ml AND a successfully
        # registered MLflow model.
        champion = resolve_scoring_engine(settings=s, thresholds=thresholds)
        challenger = resolve_challenger(settings=s, thresholds=thresholds)
        cache = PostgresCache()
        grounding = GroundingService(settings=s.kg, cache=cache) if s.kg.enabled else None

        return cls(
            settings=s,
            pool=pool,
            cache=cache,
            object_store=build_object_store(s.object_store),
            llm_factory=factory,
            thresholds=thresholds,
            engine=MultiFactorScoringEngine(thresholds),
            notification_dispatcher=dispatcher,
            scoring_engine=champion,
            challenger_engine=challenger,
            grounding_service=grounding,
        )

    def build_workflow(self, *, cell_limit: int | None = None) -> Workflow:
        """Build a workflow bound to this container's LLM factory + settings."""
        from limen.agents.workflows.main_workflow import (
            WorkflowDeps,
            build_landslide_workflow,
        )

        return build_landslide_workflow(
            WorkflowDeps(
                llm_factory=self.llm_factory,
                settings=self.settings,
                notification_dispatcher=self.notification_dispatcher,
                scoring_engine=self.scoring_engine,
                challenger_engine=self.challenger_engine,
                grounding_service=self.grounding_service,
            ),
            cell_limit=cell_limit,
        )


# ---------------------------------------------------------------------------
# FastAPI Depends() shims
# ---------------------------------------------------------------------------
def _get_deps(request: Request) -> AppDependencies:
    deps: AppDependencies | None = getattr(request.app.state, "deps", None)
    if deps is None:
        raise RuntimeError("AppDependencies not initialised — is the app lifespan running?")
    return deps


DepsDep = Annotated[AppDependencies, Depends(_get_deps)]


def _get_engine(deps: DepsDep) -> MultiFactorScoringEngine:
    return deps.engine


EngineDep = Annotated[MultiFactorScoringEngine, Depends(_get_engine)]


def _get_cache(deps: DepsDep) -> DistributedCache:
    return deps.cache


CacheDep = Annotated[DistributedCache, Depends(_get_cache)]


def _get_settings(deps: DepsDep) -> Settings:
    return deps.settings


SettingsDep = Annotated[Settings, Depends(_get_settings)]
