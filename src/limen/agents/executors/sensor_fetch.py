"""IoT in-situ sensor fetch — V1 no-op stub.

The conditional edge in the workflow inserts this executor only when
``settings.enable_insitu`` is true. V1.5 will replace the body with
real ingestion (Phoenix/MQTT/Telegram-bots or whichever transport we
land on); for V1 the stub records the intent and forwards the context
unchanged.
"""

from __future__ import annotations

from limen.agents.workflow_runtime.executor import Executor, handler
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext

log = get_logger(__name__)


class SensorFetchExecutor(Executor):
    """No-op stub for the IoT branch (V1.5 will implement it)."""

    def __init__(self) -> None:
        super().__init__(name="SensorFetch")

    @handler
    async def run(self, ctx: MonitoringContext) -> MonitoringContext:
        log.info(
            "executor.sensor_fetch.stub",
            aoi_id=ctx.aoi_id,
            note="V1 stub: real IoT ingestion lands in V1.5",
        )
        return ctx.with_update(sensor_payload={"stub": True, "source": "v1-noop"})
