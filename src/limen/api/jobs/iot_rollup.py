"""IoT rollup job — produces the per-cell hourly sensor features.

The MQTT ingestors write raw observations; this job converts them into
the per-cell aggregate the workflow's :class:`SensorFetchExecutor`
reads. It runs only when ``settings.enable_insitu`` is true.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from limen.api.dependencies import AppDependencies
from limen.core.logging import get_logger
from limen.integrations.iot.rollup import run_hourly_rollup

log = get_logger(__name__)


def ore_da_rifare(adesso: datetime, *, coda: timedelta) -> list[datetime]:
    """L'ora in corso, e la precedente finché ``coda`` non è passata.

    Una misura delle 11:55 ricevuta alle 12:05 è ancora in tempo reale, ma il
    giro delle 12:05 lavora sull'ora 12:00: senza rifare le 11:00 quella
    misura non entrerebbe in nessun rollup (#252). La coda è la tolleranza
    del ritardo più un intervallo del job, così l'ultimo giro utile cade dopo
    l'ultimo arrivo ancora in tempo reale.
    """
    ora = adesso.replace(minute=0, second=0, microsecond=0)
    if adesso - ora < coda:
        return [ora - timedelta(hours=1), ora]
    return [ora]


async def run_iot_rollup_job(deps: AppDependencies) -> int:
    """Roll the current hour (and the previous one while it can still change).
    Returns rows written."""
    if not deps.settings.enable_insitu:
        log.debug("job.iot_rollup.skip_disabled")
        return 0
    iot = deps.settings.iot
    coda = timedelta(minutes=iot.cittadini.ritardo_minuti + iot.rollup_minutes)
    written = 0
    for reference in ore_da_rifare(datetime.now(UTC), coda=coda):
        rows = await run_hourly_rollup(reference=reference)
        log.info("job.iot_rollup.done", reference=reference.isoformat(), rows=rows)
        written += rows
    return written
