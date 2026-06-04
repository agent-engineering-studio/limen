"""IoT rollup job — produces the per-cell hourly sensor features.

The MQTT ingestor writes raw observations; this job converts them into
the per-cell aggregate the workflow's :class:`SensorFetchExecutor`
reads. Both run only when ``settings.enable_insitu`` is true.
"""

from __future__ import annotations

from datetime import UTC, datetime

from limen.api.dependencies import AppDependencies
from limen.core.logging import get_logger
from limen.integrations.iot.rollup import run_hourly_rollup

log = get_logger(__name__)


async def run_iot_rollup_job(deps: AppDependencies) -> int:
    """Roll the most recently completed hour. Returns rows written."""
    if not deps.settings.enable_insitu:
        log.debug("job.iot_rollup.skip_disabled")
        return 0
    # The rollup job always targets the hour that just closed.
    reference = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    written = await run_hourly_rollup(reference=reference)
    log.info("job.iot_rollup.done", reference=reference.isoformat(), rows=written)
    return written
