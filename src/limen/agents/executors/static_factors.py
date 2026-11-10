"""Load static factors per cell (``cell_static_factors`` + susceptibility + InSAR)."""

from __future__ import annotations

from limen.agents.workflow_runtime.executor import Executor, handler
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext
from limen.core.models.hazard import DEFAULT_HAZARD, HazardType
from limen.data.repos.cell_static_factors_repo import fattori_aoi

log = get_logger(__name__)


class StaticFactorsExecutor(Executor):
    """Materialise :class:`StaticFactors` for every cell in the AOI."""

    def __init__(self, *, hazard: HazardType = DEFAULT_HAZARD) -> None:
        super().__init__(name="StaticFactors")
        # Fase 1 reads the same columns for every hazard; Fase 2 will select
        # per-hazard ones (CORINE fuel for wildfire, pai_hydraulic for flood).
        # Carried now so the workflow wiring is done once.
        self._hazard = hazard

    @handler
    async def run(self, ctx: MonitoringContext) -> MonitoringContext:
        by_cell = {sf.cell_id: sf for sf, _lon, _lat in await fattori_aoi(ctx.aoi_id)}

        log.info(
            "executor.static_factors",
            aoi_id=ctx.aoi_id,
            cells_with_factors=len(by_cell),
            cells_requested=len(ctx.cell_ids),
        )
        return ctx.with_update(static_by_cell=by_cell)
