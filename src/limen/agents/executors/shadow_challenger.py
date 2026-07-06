"""Shadow-challenger executor (V2).

Runs the challenger engine over the same bundles the champion just
scored, persists the predictions to :sql:`model_runs`, and **never**
mutates ``ctx.cell_results`` or ``ctx.assessment``. The downstream
``PersistResult`` + ``AlertDispatch`` only see the champion's output.

The executor is a no-op when ``SCORING__MODE`` is not ``shadow``.
"""

from __future__ import annotations

from limen.agents.workflow_runtime.executor import Executor, handler
from limen.core.features.assembler import assemble_bundles
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext
from limen.core.scoring.base import ScoringEngine
from limen.data.repos.model_runs_repo import ModelRunRow
from limen.data.repos.model_runs_repo import insert_many as insert_model_runs

log = get_logger(__name__)


class ShadowChallengerExecutor(Executor):
    """Compute challenger predictions and log them — never mutate cell_results."""

    def __init__(self, challenger: ScoringEngine | None) -> None:
        super().__init__(name="ShadowChallenger")
        self._challenger = challenger

    @handler
    async def run(self, ctx: MonitoringContext) -> MonitoringContext:
        if self._challenger is None:
            return ctx

        # Surface a model URI / version when the challenger is the V2
        # engine; the deterministic challenger gets a stable placeholder
        # so the model_runs table can still index by role.
        model_uri = getattr(self._challenger, "model_uri", "scoring://deterministic")
        model_version = getattr(self._challenger, "model_version", "v1-deterministic")

        bundles = assemble_bundles(ctx)
        feature_row_fn = getattr(self._challenger, "feature_row", None)
        rows: list[ModelRunRow] = []
        for bundle in bundles:
            scored = self._challenger.score(bundle)
            breakdown = scored.breakdown.model_dump(mode="json")
            if feature_row_fn is not None:
                # Canonical model inputs → drift monitoring compares
                # training vs live on identical keys and scales.
                breakdown["features"] = feature_row_fn(bundle)
            q90 = getattr(self._challenger, "conformal_q90", None)
            if q90 is not None:
                breakdown["conformal_q90"] = q90
            rows.append(
                ModelRunRow(
                    cell_id=bundle.cell_id,
                    valuation_time=ctx.valuation_time,
                    aoi_id=ctx.aoi_id,
                    model_uri=model_uri,
                    model_version=model_version,
                    role="challenger",
                    probability=scored.score,
                    risk_class=scored.level.value,
                    breakdown=breakdown,
                )
            )

        if rows:
            try:
                await insert_model_runs(rows)
            except Exception as exc:  # never let the shadow break the workflow
                log.warning(
                    "shadow_challenger.persist_failed",
                    error=str(exc),
                    error_type=type(exc).__name__,
                )

        log.info(
            "executor.shadow_challenger.done",
            aoi_id=ctx.aoi_id,
            cells=len(rows),
            model_uri=model_uri,
            model_version=model_version,
        )
        # Crucially: return the context UNCHANGED. The champion's
        # cell_results and assessment are the only authoritative outputs.
        return ctx
