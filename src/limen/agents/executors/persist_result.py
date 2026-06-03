"""Persist the assessment to ``risk_assessments``.

Writes **one row per evaluated cell** (Phase 1 schema) plus rolls a
single AOI-level row keyed by the assessment's top cell for quick
look-ups in the FastAPI tile endpoint (Phase 5).

The pipeline_version + dataset_versions array link the persisted score
back to the YAML config that produced it. dataset_versions is left
empty in V1 because the per-cell scoring doesn't yet pin to specific
ingest snapshots; that becomes a follow-on once the MAF scheduler
records its inputs.
"""

from __future__ import annotations

import json

from limen.agents.workflow_runtime.executor import Executor, handler
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext
from limen.data.db import acquire

log = get_logger(__name__)


_INSERT_SQL = """
INSERT INTO risk_assessments (
    cell_id, computed_at, horizon, score, class, factors,
    explanation, pipeline_version, dataset_versions
) VALUES ($1, now(), $2, $3, $4, $5::jsonb, $6::jsonb, $7, ARRAY[]::bigint[])
RETURNING id
"""


class PersistResultExecutor(Executor):
    """Writes one ``risk_assessments`` row per scored cell."""

    def __init__(self, *, horizon: str = "24h") -> None:
        super().__init__(name="PersistResult")
        self._horizon = horizon

    @handler
    async def run(self, ctx: MonitoringContext) -> MonitoringContext:
        assessment = ctx.assessment
        if assessment is None:
            log.warning("executor.persist_result.skip", reason="no assessment in ctx")
            return ctx

        # The AOI-level briefing is folded into every cell's explanation
        # blob so an analyst can answer "why?" from a single row.
        analysis_payload = (
            assessment.analysis.model_dump() if assessment.analysis is not None else None
        )

        last_id: int | None = None
        async with acquire() as conn, conn.transaction():
            for cell in ctx.cell_results:
                factors = {
                    "s": cell.s,
                    "m": cell.m,
                    "e": cell.e,
                    "f": cell.f,
                    "h": cell.h,
                    "static_terms": cell.static_terms.model_dump(),
                    "meteo_terms": cell.meteo_terms.model_dump(),
                }
                explanation = {
                    "model_version": assessment.model_version,
                    "valuation_time": assessment.valuation_time.isoformat(),
                    "analysis": analysis_payload,
                    "briefing_it": assessment.briefing_it,
                }
                row = await conn.fetchrow(
                    _INSERT_SQL,
                    cell.cell_id,
                    self._horizon,
                    cell.score,
                    cell.level.value,
                    json.dumps(factors, default=str),
                    json.dumps(explanation, default=str),
                    assessment.pipeline_version,
                )
                if row is not None:
                    last_id = int(row["id"])

        log.info(
            "executor.persist_result",
            aoi_id=ctx.aoi_id,
            cells_persisted=len(ctx.cell_results),
            last_id=last_id,
        )
        return ctx.with_update(assessment_id=last_id)
