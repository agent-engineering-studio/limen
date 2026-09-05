"""Run the deterministic scoring engine for every cell in the AOI.

This is the **authoritative** numeric step of the workflow. Anything
downstream (ChatAgents, persist, alert) only reformulates / consumes
these numbers; it never alters them.
"""

from __future__ import annotations

import asyncio
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
from limen.core.models.hazard import DEFAULT_HAZARD, HazardType
from limen.core.models.risk import HazardBreakdown, RiskLevel
from limen.core.scoring.base import ScoringEngine
from limen.core.scoring.engine import MultiFactorScoringEngine
from limen.core.scoring.regional_thresholds import (
    HazardThresholds,
    RegionalThresholds,
    load_hazard_thresholds,
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


def _default_engine(thresholds: HazardThresholds) -> ScoringEngine[HazardBreakdown]:
    """The V1 landslide engine, for callers that inject no engine.

    Only the landslide baseline can be built without going through the
    registry, because it is the only one this module knows how to construct.
    Any other hazard reaching here without an injected engine is a wiring
    bug: the workflow resolves one per hazard before building the executor.
    """
    if not isinstance(thresholds, RegionalThresholds):
        raise TypeError(
            "RiskScoringExecutor can only build the landslide baseline itself; "
            f"pass engine= for a hazard configured by {type(thresholds).__name__}"
        )
    return MultiFactorScoringEngine(thresholds)


class RiskScoringExecutor(Executor):
    """Build bundles → score every cell → roll up an :class:`AggregateAssessment`."""

    def __init__(
        self,
        *,
        thresholds: HazardThresholds | None = None,
        engine: ScoringEngine[HazardBreakdown] | None = None,
        top_k: int = 10,
        macroregion: str = "italy_default",
        hazard: HazardType = DEFAULT_HAZARD,
    ) -> None:
        super().__init__(name="RiskScoring")
        self._hazard = hazard
        # Each hazard has its own YAML: loading the landslide file for a flood
        # sweep would score with slope-failure thresholds.
        self._thresholds: HazardThresholds = thresholds or load_hazard_thresholds(hazard)
        # ``engine`` lets the workflow inject the resolver-selected engine
        # (V1 by default, V2 ML when promoted). Without an injection we
        # fall back to the deterministic engine — the V1 champion stays
        # the only behaviour any consumer sees by default.
        self._engine: ScoringEngine[HazardBreakdown] = engine or _default_engine(
            self._thresholds
        )
        self._top_k = top_k
        self._macroregion = macroregion

    def _score_all(self, ctx: MonitoringContext) -> list[CellRiskRecord]:
        """CPU-bound loop over every cell — runs in a worker thread.

        The hourly job lives in the SAME process as the API: scoring
        312k cells inline blocked the event loop for minutes and every
        HTTP request during a sweep timed out.
        """
        bundles = assemble_bundles(ctx, macroregion=self._macroregion)
        records: list[CellRiskRecord] = []
        for bundle in bundles:
            scored = self._engine.score(bundle)
            records.append(
                CellRiskRecord(
                    cell_id=bundle.cell_id,
                    hazard_type=self._hazard,
                    score=scored.score,
                    level=scored.level,
                    breakdown=scored.breakdown,
                    monitored=scored.monitored,
                    hard_escalation=scored.hard_escalation,
                )
            )

        # Sort by descending score so top-K is easy
        records.sort(key=lambda r: r.score, reverse=True)
        return records

    @handler
    async def run(self, ctx: MonitoringContext) -> MonitoringContext:
        records = await asyncio.to_thread(self._score_all, ctx)
        by_level = Counter(r.level.value for r in records)
        high_or_above = sum(
            1 for r in records if _level_rank(r.level) >= _level_rank(RiskLevel.High)
        )

        assessment = AggregateAssessment(
            aoi_id=ctx.aoi_id,
            hazard_type=self._hazard,
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
