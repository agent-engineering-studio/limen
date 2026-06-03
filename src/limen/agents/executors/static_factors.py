"""Load static factors per cell from ``cell_static_factors``."""

from __future__ import annotations

from limen.agents.workflow_runtime.executor import Executor, handler
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext
from limen.core.models.risk import StaticFactors
from limen.data.db import acquire

log = get_logger(__name__)


_SELECT_SQL = """
SELECT c.cell_id,
       c.slope_deg, c.aspect_deg, c.elevation_m, c.twi, c.curvature,
       c.lithology, c.land_cover, c.landuse_code,
       c.litho_weight, c.dist_faults_m,
       c.distance_to_iffi_m, c.iffi_density_500,
       c.pai_class_norm,
       s.score AS susc_ispra
FROM cell_static_factors c
JOIN grid_cells g ON g.id = c.cell_id
LEFT JOIN susceptibility s ON s.cell_id = c.cell_id
WHERE g.aoi_id = $1
"""


class StaticFactorsExecutor(Executor):
    """Materialise :class:`StaticFactors` for every cell in the AOI."""

    def __init__(self) -> None:
        super().__init__(name="StaticFactors")

    @handler
    async def run(self, ctx: MonitoringContext) -> MonitoringContext:
        async with acquire() as conn:
            rows = await conn.fetch(_SELECT_SQL, ctx.aoi_id)

        by_cell: dict[str, StaticFactors] = {}
        for r in rows:
            cid = str(r["cell_id"])
            by_cell[cid] = StaticFactors(
                cell_id=cid,
                susc_ispra=float(r["susc_ispra"]) if r["susc_ispra"] is not None else None,
                iffi_density_500=(
                    float(r["iffi_density_500"]) if r["iffi_density_500"] is not None else None
                ),
                distance_to_iffi_m=(
                    float(r["distance_to_iffi_m"]) if r["distance_to_iffi_m"] is not None else None
                ),
                slope_deg=float(r["slope_deg"]) if r["slope_deg"] is not None else None,
                aspect_deg=float(r["aspect_deg"]) if r["aspect_deg"] is not None else None,
                elevation_m=float(r["elevation_m"]) if r["elevation_m"] is not None else None,
                twi=float(r["twi"]) if r["twi"] is not None else None,
                curvature=float(r["curvature"]) if r["curvature"] is not None else None,
                lithology=r["lithology"],
                litho_weight=(float(r["litho_weight"]) if r["litho_weight"] is not None else None),
                landuse_code=r["landuse_code"],
                pai_class_norm=(
                    float(r["pai_class_norm"]) if r["pai_class_norm"] is not None else None
                ),
            )

        log.info(
            "executor.static_factors",
            aoi_id=ctx.aoi_id,
            cells_with_factors=len(by_cell),
            cells_requested=len(ctx.cell_ids),
        )
        return ctx.with_update(static_by_cell=by_cell)
