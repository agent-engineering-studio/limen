"""Build the main Limen landslide-risk workflow.

Pipeline (§3.2):

    AreaResolver → StaticFactors → MeteoFetch → SeismicCheck → FireCheck
    [→ SensorFetch if settings.enable_insitu]
    → RiskScoring → EscalationGate → RiskAnalystNode → BriefingNode
    → PersistResult → AlertDispatch

The two LLM-backed nodes (RiskAnalystNode, BriefingNode) are wrapped
as :class:`Executor` so the workflow stays a uniform sequence of
executors, but they are **non-authoritative**: they only annotate the
already-computed numeric breakdown.

Tests assert this invariance: with vs without the LLM step, the
numeric ``cell_results`` are identical.
"""

from __future__ import annotations

from dataclasses import dataclass

from limen.agents.chat_agents.briefing import BriefingAgent
from limen.agents.chat_agents.risk_analyst import RiskAnalystAgent
from limen.agents.executors import (
    AlertDispatchExecutor,
    AreaResolverExecutor,
    EscalationGateExecutor,
    FireCheckExecutor,
    MeteoFetchExecutor,
    PersistResultExecutor,
    RiskScoringExecutor,
    SeismicCheckExecutor,
    SensorFetchExecutor,
    StaticFactorsExecutor,
)
from limen.agents.llm_factory.base import LlmClientFactory
from limen.agents.workflow_runtime.builder import Workflow, WorkflowBuilder
from limen.agents.workflow_runtime.executor import Executor, handler
from limen.config.settings import Settings, get_settings
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext

log = get_logger(__name__)


@dataclass(slots=True)
class WorkflowDeps:
    """Runtime dependencies the workflow needs at build time."""

    llm_factory: LlmClientFactory
    settings: Settings


# ---------------------------------------------------------------------------
# LLM nodes wrapped as executors
# ---------------------------------------------------------------------------
class RiskAnalystNode(Executor):
    """Executor wrapper around :class:`RiskAnalystAgent`."""

    def __init__(self, llm_factory: LlmClientFactory) -> None:
        super().__init__(name="RiskAnalyst")
        self._agent = RiskAnalystAgent(llm_factory.create("RiskAnalyst"))

    @handler
    async def run(self, ctx: MonitoringContext) -> MonitoringContext:
        if ctx.assessment is None:
            log.warning("workflow.risk_analyst.skip", reason="no assessment in ctx")
            return ctx
        analysis = await self._agent.analyse(ctx.assessment)
        from limen.core.models.context import RiskAnalysisDTO

        analysis_dto = RiskAnalysisDTO.model_validate(analysis.model_dump())
        log.info(
            "workflow.risk_analyst.done",
            driver=analysis_dto.driver,
            attention_window_hours=analysis_dto.attention_window_hours,
            confidence=analysis_dto.confidence,
            anomalies=len(analysis_dto.anomalies),
        )
        updated = ctx.assessment.model_copy(update={"analysis": analysis_dto})
        return ctx.with_update(assessment=updated)


class BriefingNode(Executor):
    """Executor wrapper around :class:`BriefingAgent`."""

    def __init__(self, llm_factory: LlmClientFactory) -> None:
        super().__init__(name="Briefing")
        self._agent = BriefingAgent(llm_factory.create("Briefing"))

    @handler
    async def run(self, ctx: MonitoringContext) -> MonitoringContext:
        if ctx.assessment is None:
            log.warning("workflow.briefing.skip", reason="no assessment in ctx")
            return ctx
        # The Briefing prompt reads the (possibly missing) RiskAnalyst output.
        # We map the DTO back to the strict RiskAnalysis model when present.
        from limen.agents.chat_agents.risk_analyst import RiskAnalysis

        analysis = (
            RiskAnalysis.model_validate(ctx.assessment.analysis.model_dump())
            if ctx.assessment.analysis is not None
            else None
        )
        text = await self._agent.brief(ctx.assessment, analysis=analysis)
        log.info("workflow.briefing.done", chars=len(text))
        updated = ctx.assessment.model_copy(update={"briefing_it": text})
        return ctx.with_update(assessment=updated)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------
def build_landslide_workflow(
    deps: WorkflowDeps | None = None,
    *,
    cell_limit: int | None = None,
) -> Workflow:
    """Assemble the sequential workflow.

    ``cell_limit`` is exposed mainly for tests / smoke runs where
    scoring 60k cells per AOI would be wasteful.
    """
    deps = deps or WorkflowDeps(
        llm_factory=_default_factory(),
        settings=get_settings(),
    )
    settings = deps.settings

    builder = (
        WorkflowBuilder("limen-landslide-v1")
        .add(AreaResolverExecutor(cell_limit=cell_limit))
        .add(StaticFactorsExecutor())
        .add(MeteoFetchExecutor())
        .add(SeismicCheckExecutor())
        .add(FireCheckExecutor())
    )
    # IoT branch — conditional on the settings toggle. The shim's
    # add_if reads the predicate against the context at run time, so we
    # use a closure over the *runtime* enable_insitu flag stored in the
    # context (the AreaResolver doesn't set it, so we project the
    # settings value through `with_update`).
    sensor = SensorFetchExecutor()
    builder = builder.add_if(lambda ctx: bool(getattr(ctx, "enable_insitu", False)), sensor)

    builder = (
        builder.add(RiskScoringExecutor())
        .add(EscalationGateExecutor())
        .add(RiskAnalystNode(deps.llm_factory))
        .add(BriefingNode(deps.llm_factory))
        .add(PersistResultExecutor())
        .add(AlertDispatchExecutor())
    )
    log.info(
        "workflow.built",
        name="limen-landslide-v1",
        steps=builder.build().step_count,
        enable_insitu=settings.enable_insitu,
        llm_provider=deps.llm_factory.provider,
    )
    return builder.build()


def _default_factory() -> LlmClientFactory:
    """Late-bind to keep test imports independent of LLM env state."""
    from limen.agents.llm_factory.resolver import resolve_llm_factory

    return resolve_llm_factory()
