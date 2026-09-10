"""``limen worker`` — il processo dei batch, separato dall'API (#77).

Stessa immagine, due container: `api` serve HTTP e basta, `worker` esegue lo
scheduler e basta. Prima erano lo stesso processo, e il commento in
`risk_scoring.py` racconta come andava a finire — l'API in timeout durante lo
sweep, con `asyncio.to_thread` come cerotto. Un solo event loop non può
servire una mappa pubblica e macinare 312.000 celle allo stesso tempo.

**Il worker non applica le migrazioni: le attende.** Due processi che migrano
insieme sono una corsa, e il perdente trova la tabella già creata a metà. Le
applica `limen migrate` (o l'API al boot); qui si controlla che lo schema
atteso ci sia, con backoff, e si parte solo quando c'è. È anche ciò che rende
sicuro un `restart: unless-stopped`: un worker che riparte prima dell'API non
corrompe niente, aspetta.

Env:

* ``LIMEN_WORKER_HEARTBEAT_SECONDS`` — cadenza del battito (default 60).
* ``LIMEN_WORKER_HEALTH_MAX_AGE_SECONDS`` — quanto può essere vecchio il
  battito perché ``--health`` dica ancora "vivo" (default 180).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
from datetime import UTC, datetime
from typing import Any

from limen.api.dependencies import AppDependencies
from limen.api.jobs.registration import register_jobs
from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.data.db import close_pool, get_pool, init_pool
from limen.data.repos import job_runs_repo

log = get_logger(__name__)

#: Job id del battito. Vive nella stessa `job_runs` di tutto il resto, così
#: `limen jobs` mostra anche "il worker è vivo" senza una tabella in più.
HEARTBEAT_JOB = "limen-worker-heartbeat"

_MIGRATION_WAIT_MAX_S = 300.0


def _heartbeat_seconds() -> float:
    return float(os.getenv("LIMEN_WORKER_HEARTBEAT_SECONDS", "60"))


def _health_max_age_seconds() -> float:
    return float(os.getenv("LIMEN_WORKER_HEALTH_MAX_AGE_SECONDS", "180"))


async def _wait_for_schema(*, timeout_s: float = _MIGRATION_WAIT_MAX_S) -> bool:
    """Attende che le migrazioni siano applicate. Backoff, mai applicare."""
    from limen.data.db import acquire

    delay = 1.0
    waited = 0.0
    while waited < timeout_s:
        try:
            async with acquire() as conn:
                ok = await conn.fetchval("SELECT to_regclass('public.job_runs') IS NOT NULL")
            if ok:
                return True
        except Exception as exc:
            log.info("worker.schema.waiting", error=str(exc))
        await asyncio.sleep(delay)
        waited += delay
        delay = min(delay * 2, 15.0)
    return False


async def _heartbeat_loop(stop: asyncio.Event) -> None:
    """Una riga in `job_runs` a intervalli, finché non arriva lo stop."""
    period = _heartbeat_seconds()
    while not stop.is_set():
        run_id = await job_runs_repo.start(HEARTBEAT_JOB)
        await job_runs_repo.finish(run_id, status="ok", metrics={"period_s": period})
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=period)


async def health() -> int:
    """``limen worker --health``: 0 se il battito è recente, 1 altrimenti.

    Legge il database e non un file di lock: l'healthcheck deve dire che il
    worker **sta lavorando**, non che il suo processo esiste — un worker con
    l'event loop bloccato ha ancora il PID.
    """
    settings = get_settings()
    await init_pool(settings.db)
    try:
        runs = await job_runs_repo.recent(HEARTBEAT_JOB, limit=1)
    finally:
        await close_pool()
    if not runs:
        log.warning("worker.health.no_heartbeat")
        return 1
    last = runs[0].finished_at or runs[0].started_at
    age = (datetime.now(UTC) - last).total_seconds()
    limit = _health_max_age_seconds()
    log.info("worker.health", age_s=round(age, 1), limit_s=limit)
    return 0 if age <= limit else 1


async def run(*, check_health: bool = False) -> int:
    """Avvia lo scheduler e resta in ascolto fino a SIGTERM."""
    if check_health:
        return await health()

    from apscheduler import AsyncScheduler

    settings = get_settings()
    await init_pool(settings.db)
    if not await _wait_for_schema():
        log.error("worker.schema.timeout", note="le migrazioni non risultano applicate")
        await close_pool()
        return 1

    deps = await AppDependencies.build(pool=get_pool(), settings=settings)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    ingestor: Any = None
    heartbeat: asyncio.Task[None] | None = None
    async with AsyncScheduler() as scheduler:
        registered = await register_jobs(scheduler, deps)
        await scheduler.start_in_background()
        log.info("worker.started", jobs=len(registered))

        if settings.enable_insitu:
            from limen.integrations.iot.mqtt_ingestor import MqttIngestor

            sigma_v = (
                deps.thresholds.kinematic.sigma_v if deps.thresholds.kinematic is not None else None
            )
            ingestor = MqttIngestor(settings.iot, sigma_v=sigma_v)
            await ingestor.start()
            log.info("worker.iot.started")

        heartbeat = asyncio.create_task(_heartbeat_loop(stop))
        await stop.wait()
        log.info("worker.stopping")

        if heartbeat is not None:
            heartbeat.cancel()
            with contextlib.suppress(BaseException):
                await heartbeat
        if ingestor is not None:
            with contextlib.suppress(Exception):
                await ingestor.stop()
        with contextlib.suppress(Exception):
            await scheduler.stop()

    from limen.integrations._http import SharedHttpClient

    await SharedHttpClient.aclose()
    await close_pool()
    log.info("worker.stopped")
    return 0


def main() -> int:
    return asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
