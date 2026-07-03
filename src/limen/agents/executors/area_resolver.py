"""AOI id → geometry + active grid cells."""

from __future__ import annotations

from limen.agents.workflow_runtime.executor import Executor, handler
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext
from limen.data.db import acquire
from limen.data.repos.aoi_repo import get_aoi

log = get_logger(__name__)


class AreaResolverExecutor(Executor):
    """Loads the AOI bbox and the active grid-cell ids into the context."""

    def __init__(self, *, cell_limit: int | None = None) -> None:
        super().__init__(name="AreaResolver")
        self._cell_limit = cell_limit

    @handler
    async def run(self, ctx: MonitoringContext) -> MonitoringContext:
        aoi = await get_aoi(ctx.aoi_id)
        if aoi is None:
            raise RuntimeError(f"AOI {ctx.aoi_id!r} not found")

        bounds = aoi.bbox.bounds
        bbox = (float(bounds[0]), float(bounds[1]), float(bounds[2]), float(bounds[3]))

        sql = (
            "SELECT id, ST_X(ST_Centroid(geom)) AS lon, ST_Y(ST_Centroid(geom)) AS lat "
            "FROM grid_cells WHERE aoi_id = $1 ORDER BY id"
        )
        if self._cell_limit is not None:
            sql += f" LIMIT {int(self._cell_limit)}"

        async with acquire() as conn:
            rows = await conn.fetch(sql, ctx.aoi_id)
        cells = tuple(str(r["id"]) for r in rows)
        centroids = {str(r["id"]): (float(r["lon"]), float(r["lat"])) for r in rows}

        log.info("executor.area_resolver", aoi_id=ctx.aoi_id, cells=len(cells))
        return ctx.with_update(bbox=bbox, cell_ids=cells, cell_centroids=centroids)
