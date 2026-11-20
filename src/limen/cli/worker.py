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
* ``LIMEN_WORKER_WATCHDOG_SECONDS`` — dopo quanto senza un battito riuscito il
  worker esce da sé, perché Docker lo riavvii (default 900).
* ``WORKER__INTERRUZIONE_MINUTI`` / ``WORKER__PING_URL`` — quando un buco fra
  due battiti è un'interruzione da segnalare, e il monitor esterno che vede
  il worker fermo mentre lo è (#655).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import signal
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from limen.api.dependencies import AppDependencies
from limen.api.jobs.ids import JOB_WORKER_HEARTBEAT, JOB_WORKER_INTERRUZIONE
from limen.api.jobs.registration import register_jobs
from limen.config.percorsi import radice_dati
from limen.config.settings import Settings, get_settings
from limen.core.logging import get_logger
from limen.data.db import close_pool, get_pool, init_pool
from limen.data.repos import job_runs_repo, salute_repo
from limen.integrations import salute
from limen.integrations._http import fetch_with_retry
from limen.notifications.email import invia_testo

log = get_logger(__name__)

#: Job id del battito. Vive nella stessa `job_runs` di tutto il resto, così
#: `limen jobs` mostra anche "il worker è vivo" senza una tabella in più.
HEARTBEAT_JOB = JOB_WORKER_HEARTBEAT

_MIGRATION_WAIT_MAX_S = 300.0


def _heartbeat_seconds() -> float:
    return float(os.getenv("LIMEN_WORKER_HEARTBEAT_SECONDS", "60"))


def _health_max_age_seconds() -> float:
    return float(os.getenv("LIMEN_WORKER_HEALTH_MAX_AGE_SECONDS", "180"))


def _watchdog_seconds() -> float:
    return float(os.getenv("LIMEN_WORKER_WATCHDOG_SECONDS", "900"))


class Sentinella:
    """Esce dal processo se il battito non riesce per ``limite`` secondi.

    L'healthcheck vede un worker fermo, ma Docker fuori da Swarm non riavvia
    un container *unhealthy*: `restart: unless-stopped` scatta solo se il
    processo esce. Il 13/11/2026 il worker è rimasto fermo dalle 03:46 alle
    10:06 UTC — niente sweep, previsione delle 08:20 e raccolta eventi perse —
    finché non è stato ricreato a mano. È un thread e non un task: un event
    loop bloccato non eseguirebbe un task che lo sorveglia.
    """

    def __init__(self, limite: float, uscita: Callable[[int], object] = os._exit) -> None:
        self.limite = limite
        self._uscita = uscita
        self._ultimo = time.monotonic()
        self._fermo = threading.Event()

    def battito(self) -> None:
        self._ultimo = time.monotonic()

    def eta(self) -> float:
        return time.monotonic() - self._ultimo

    def ferma(self) -> None:
        self._fermo.set()

    def sorveglia(self, passo: float = 60.0) -> None:
        while not self._fermo.wait(min(passo, self.limite / 4)):
            if self.eta() > self.limite:
                log.error(
                    "worker.sentinella.scaduta", eta_s=round(self.eta()), limite_s=self.limite
                )
                self._uscita(1)
                return

    def avvia(self) -> threading.Thread:
        filo = threading.Thread(target=self.sorveglia, name="sentinella", daemon=True)
        filo.start()
        return filo


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


async def _publish_next_fire(scheduler: Any, period: float) -> None:
    """Scrive l'orario del prossimo scatto di ogni job registrato.

    L'API non lo può leggere da sé: lo scheduler vive in memoria in questo
    processo, e dedurlo dall'ultima corsa (`started_at + intervallo`) sbaglia
    proprio dopo un riavvio, quando `_deferred_interval` sposta il primo
    scatto a un intervallo dal boot — cioè quando qualcuno guarda il timer.

    Con una scadenza di tre battiti: se il worker muore il valore sparisce,
    e l'API dice «non lo so» invece di mostrare un conto alla rovescia verso
    un calcolo che nessuno farà.
    """
    from limen.data.caching.postgres_cache import PostgresCache
    from limen.data.repos.forecast_schedule import NEXT_FIRE_KEY

    try:
        prossimi = {
            str(s.id): s.next_fire_time.isoformat()
            for s in await scheduler.get_schedules()
            if s.next_fire_time is not None
        }
        await PostgresCache().set_json(
            NEXT_FIRE_KEY, prossimi, ttl_seconds=max(int(period * 3), 180)
        )
    except Exception as exc:
        log.warning("worker.next_fire.failed", error=str(exc), error_type=type(exc).__name__)


def _disco() -> dict[str, float]:
    """Lo spazio libero, per la pagina «Salute» (#408): sotto la radice dei dati
    e sul disco di Docker, dove sta il volume di Postgres (`/` del container è
    sullo stesso disco; da SQL lo spazio libero non si vede)."""
    out: dict[str, float] = {}
    for chiave, percorso in (("dati", radice_dati()), ("docker", Path("/"))):
        try:
            uso = shutil.disk_usage(percorso)
        except OSError:
            continue
        out[f"disco_{chiave}_libero_gb"] = round(uso.free / 1e9, 1)
        out[f"disco_{chiave}_totale_gb"] = round(uso.total / 1e9, 1)
    return out


async def _riversa_salute() -> None:
    """Gli esiti delle chiamate alle fonti dall'ultimo battito, in `salute_fonti`."""
    try:
        await salute_repo.riversa(salute.svuota())
    except Exception as exc:
        log.warning("worker.salute.failed", error=str(exc), error_type=type(exc).__name__)


def interruzione(
    precedente: datetime | None, adesso: datetime, soglia: timedelta
) -> datetime | None:
    """L'inizio del buco, se fra l'ultimo battito riuscito e questo c'è più di ``soglia``."""
    if precedente is None or adesso - precedente <= soglia:
        return None
    return precedente


async def _ultimo_battito() -> datetime | None:
    """L'ultimo battito riuscito nel database: un buco attraversa anche un riavvio."""
    for run in await job_runs_repo.recent(HEARTBEAT_JOB, limit=5):
        if run.status == "ok":
            return run.started_at
    return None


async def _segnala_interruzione(dal: datetime, al: datetime, settings: Settings) -> None:
    """Una riga in ``job_runs``, un log d'errore e una mail a chi cura il progetto."""
    ore = round((al - dal).total_seconds() / 3600, 1)
    testo = (
        f"Il worker di Limen non ha battuto dal {dal:%d/%m/%Y %H:%M} al {al:%d/%m/%Y %H:%M} UTC "
        f"({ore} ore). In quel periodo non sono girati sweep, previsioni per cella, "
        "passo notturno e backup: gli eventi di quei giorni risulteranno non verificabili. "
        "Se la macchina era sospesa, va tolto il risparmio energetico."
    )
    log.error("worker.interruzione", dal=dal.isoformat(), al=al.isoformat(), ore=ore)
    run_id = await job_runs_repo.start(JOB_WORKER_INTERRUZIONE)
    await job_runs_repo.finish(
        run_id,
        status="error",
        metrics={"dal": dal.isoformat(), "al": al.isoformat(), "ore": ore},
        error=testo,
    )
    await invia_testo(
        settings.notifications.email,
        destinatari=settings.contributi.destinatari,
        oggetto=f"Limen: worker fermo per {ore} ore",
        testo=testo,
    )


async def _ping(url: str) -> None:
    """Il monitor esterno: un ping fallito non tocca il battito."""
    try:
        risposta = await asyncio.wait_for(fetch_with_retry("GET", url), timeout=30)
    except Exception as exc:
        log.warning("worker.ping.failed", error=str(exc)[:200], error_type=type(exc).__name__)
        return
    # Un 4xx non si ripete e non solleva: un token di push sbagliato
    # lascerebbe il monitor rosso senza una riga nei log.
    if risposta.status_code >= 400:
        log.warning("worker.ping.failed", status=risposta.status_code)


def soglia_interruzione(minuti: int, watchdog_s: float) -> timedelta:
    """Mai sotto un riavvio da sentinella: il watchdog, l'attesa dello schema e
    cinque minuti di margine. Alzare il watchdog non deve far partire una mail
    a ogni riavvio."""
    riavvio = timedelta(seconds=watchdog_s + _MIGRATION_WAIT_MAX_S) + timedelta(minutes=5)
    return max(timedelta(minutes=minuti), riavvio)


async def _heartbeat_loop(
    stop: asyncio.Event,
    scheduler: Any = None,
    sentinella: Sentinella | None = None,
    settings: Settings | None = None,
) -> None:
    """Una riga in `job_runs` a intervalli, finché non arriva lo stop."""
    period = _heartbeat_seconds()
    impostazioni = settings or get_settings()
    soglia = soglia_interruzione(impostazioni.worker.interruzione_minuti, _watchdog_seconds())
    precedente: datetime | None = None
    letto = False
    while not stop.is_set():
        # Un timeout del database non deve uccidere il battito: il task
        # morirebbe in silenzio e il worker, vivo, risulterebbe fermo.
        try:
            if not letto:
                precedente = await _ultimo_battito()
            adesso = datetime.now(UTC)
            run_id = await job_runs_repo.start(HEARTBEAT_JOB)
            await job_runs_repo.finish(
                run_id, status="ok", metrics={"period_s": period, **_disco()}
            )
            # `start` degrada a None invece di sollevare: senza la riga il
            # battito non è riuscito, e né il buco né il ping si toccano. La
            # prima lettura conta solo se il database ha risposto.
            if run_id is None:
                raise RuntimeError("battito non scritto")
            letto = True
            if sentinella is not None:
                sentinella.battito()
            if (dal := interruzione(precedente, adesso, soglia)) is not None:
                try:
                    await _segnala_interruzione(dal, adesso, impostazioni)
                except Exception as exc:
                    log.warning(
                        "worker.interruzione.failed",
                        error=str(exc)[:200],
                        error_type=type(exc).__name__,
                    )
            precedente = adesso
            if impostazioni.worker.ping_url:
                await _ping(impostazioni.worker.ping_url)
        except Exception as exc:
            log.warning("worker.heartbeat.failed", error=str(exc), error_type=type(exc).__name__)
        await _riversa_salute()
        if scheduler is not None:
            await _publish_next_fire(scheduler, period)
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

    # I file dei dati statici li scrivono in due, il worker e chi lancia
    # `make static-data` sull'host, nelle stesse cartelle setgid: con il
    # gruppo in scrittura ognuno riprende i `.part` dell'altro (#402).
    os.umask(0o002)
    settings = get_settings()
    await init_pool(settings.db)
    if not await _wait_for_schema():
        log.error("worker.schema.timeout", note="le migrazioni non risultano applicate")
        await close_pool()
        return 1

    await job_runs_repo.chiudi_interrotte(heartbeat_job=HEARTBEAT_JOB)
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

        # I dispositivi di terzi (#252) entrano solo da qui, mai dall'API, e
        # indipendentemente da `enable_insitu`: salvare una misura non la porta
        # nello scoring, lo decidono il livello (#251) e il rollup.
        ingestore_v2: Any = None
        if settings.iot.cittadini.enabled:
            from limen.integrations.iot.ingestore_v2 import IngestoreV2

            ingestore_v2 = IngestoreV2(
                settings.iot,
                sigma_v=(
                    deps.thresholds.kinematic.sigma_v
                    if deps.thresholds.kinematic is not None
                    else None
                ),
            )
            await ingestore_v2.start()
            log.info("worker.iot.v2.started")

        # I download dei dati statici (#402): partono quando qualcuno li chiede,
        # quindi non sono uno schedule — il consumatore ascolta la coda.
        scaricamenti: Any = None
        try:
            from limen.api.jobs.dati_download import ConsumatoreDownload

            scaricamenti = ConsumatoreDownload()
            await scaricamenti.start()
        except Exception as exc:  # i download non valgono lo sweep orario
            log.warning(
                "dati_download.non_avviato", error=str(exc)[:300], error_type=type(exc).__name__
            )

        sentinella = Sentinella(_watchdog_seconds())
        sentinella.avvia()
        heartbeat = asyncio.create_task(_heartbeat_loop(stop, scheduler, sentinella, settings))
        await stop.wait()
        log.info("worker.stopping")
        sentinella.ferma()

        if heartbeat is not None:
            heartbeat.cancel()
            with contextlib.suppress(BaseException):
                await heartbeat
        if scaricamenti is not None:
            await scaricamenti.stop()
        if ingestor is not None:
            with contextlib.suppress(Exception):
                await ingestor.stop()
        if ingestore_v2 is not None:
            with contextlib.suppress(Exception):
                await ingestore_v2.stop()
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
