"""IoT in-situ sensor fetch (V1.5).

Reads the most recent ``sensor_features_hourly`` row for every cell in
the AOI and stores the resulting :class:`SensorFeatures` aggregates on
``ctx.sensor_features_by_cell``. The :func:`assemble_bundles` glue
forwards them into the engine, which activates the K component and
applies the measured-over-modeled override.

V1 behaviour (no in-situ rows): the dict stays empty and the engine
runs the pure V1 path for every cell — see the invariance test
``test_v15_disabled_matches_v1``.
"""

from __future__ import annotations

from limen.agents.workflow_runtime.executor import Executor, handler
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext
from limen.core.models.sensor import SensorFeatures
from limen.data.repos import sensor_features_hourly_repo

log = get_logger(__name__)


class SensorFetchExecutor(Executor):
    """Populate per-cell :class:`SensorFeatures` from the rollup table."""

    def __init__(self) -> None:
        super().__init__(name="SensorFetch")

    @handler
    async def run(self, ctx: MonitoringContext) -> MonitoringContext:
        features: dict[str, SensorFeatures] = {}
        for cell_id in ctx.cell_ids:
            row = await sensor_features_hourly_repo.latest_for_cell(cell_id)
            if row is None:
                continue
            features[cell_id] = row.to_dto()

        log.info(
            "executor.sensor_fetch.done",
            aoi_id=ctx.aoi_id,
            cells=len(ctx.cell_ids),
            cells_with_features=len(features),
        )
        return ctx.with_update(
            sensor_features_by_cell=features,
            sensor_payload={
                "source": "sensor_features_hourly",
                "cells_with_features": len(features),
            },
        )
