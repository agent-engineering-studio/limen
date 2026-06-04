"""Monthly partition rollover for ``sensor_observations``.

Extends the rolling ±N-months window every month so the ingestor
always has a partition to insert into.
"""

from __future__ import annotations

from datetime import UTC, datetime

from limen.api.dependencies import AppDependencies
from limen.core.logging import get_logger
from limen.data.db import acquire
from limen.integrations.iot.partitions import ensure_partition_window

log = get_logger(__name__)


async def run_iot_partition_rollover_job(deps: AppDependencies) -> int:
    if not deps.settings.enable_insitu:
        log.debug("job.iot_partition_rollover.skip_disabled")
        return 0
    today = datetime.now(UTC).date()
    window = deps.settings.iot.partition_window_months
    async with acquire() as conn:
        touched = await ensure_partition_window(conn, reference=today, window_months=window)
    log.info(
        "job.iot_partition_rollover.done",
        partitions=len(touched),
        window_months=window,
    )
    return len(touched)
