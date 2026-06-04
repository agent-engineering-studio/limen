"""Run the deterministic scoring engine for every cell in the AOI.

This is the **authoritative** numeric step of the workflow. Anything
downstream (ChatAgents, persist, alert) only reformulates / consumes
these numbers; it never alters them.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

from limen.agents.workflow_runtime.executor import Executor, handler
from limen.core.features.assembler import assemble_bundles
from limen.core.logging import get_logger
from limen.core.models.context import (
    AggregateAssessment,
    CellRiskRecord,
    MonitoringContext,
)
from limen.core.models.risk import RiskLevel
from limen.core.scoring.engine import MultiFactorScoringEngine
from limen.core.scoring.regional_thresholds import (
    RegionalThresholds,
    load_regional_thresholds,
)

log = get_logger(__name__)


def _level_rank(level: RiskLevel) -> int:
    order = (
        RiskLevel.None_,
        RiskLevel.Low,
        RiskLevel.Moderate,
        RiskLevel.High,
        RiskLevel.VeryHigh,
    )
    return order.index(level)


class RiskScoringExecutor(Executor):
    """Build bundles → score every cell → roll up an :class:`AggregateAssessment`."""

    def __init__(
        self,
        *,
        thresholds: RegionalThresholds | None = None,
        top_k: int = 10,
        macroregion: str = "italy_default",
    ) -> None:
        super().__init__(name="RiskScoring")
        self._thresholds = thresholds or load_regional_thresholds()
        self._engine = MultiFactorScoringEngine(self._thresholds)
        self._top_k = top_k
        self._macroregion = macroregion

    @handler
    async def run(self, ctx: MonitoringContext) -> MonitoringContext:
        bundles = assemble_bundles(ctx, macroregion=self._macroregion)
        records: list[CellRiskRecord] = []
        for bundle in bundles:
            scored = self._engine.score(bundle)
            records.append(
                CellRiskRecord(
                    cell_id=bundle.cell_id,
                    score=scored.score,
                    level=scored.level,
                    static_terms=scored.breakdown.static_terms,
                    meteo_terms=scored.breakdown.meteo_terms,
                    s=scored.breakdown.s,
                    m=scored.breakdown.m,
                    e=scored.breakdown.e,
                    f=scored.breakdown.f,
                    h=scored.breakdown.h,
                    k=scored.breakdown.k,
                    kinematic_terms=scored.breakdown.kinematic_terms,
                    monitored=scored.monitored,
                    hard_escalation=scored.hard_escalation,
                )
            )

        # Sort by descending score so top-K is easy
        records.sort(key=lambda r: r.score, reverse=True)
        by_level = Counter(r.level.value for r in records)
        high_or_above = sum(
            1 for r in records if _level_rank(r.level) >= _level_rank(RiskLevel.High)
        )

        assessment = AggregateAssessment(
            aoi_id=ctx.aoi_id,
            model_version=self._thresholds.model_version,
            valuation_time=datetime.now(UTC),
            n_cells=len(records),
            cells_high_or_above=high_or_above,
            cells_by_level=dict(by_level),
            top_cells=records[: self._top_k],
        )

        log.info(
            "executor.risk_scoring",
            aoi_id=ctx.aoi_id,
            cells=len(records),
            high_or_above=high_or_above,
            top_score=records[0].score if records else None,
        )

        return ctx.with_update(cell_results=records, assessment=assessment)
