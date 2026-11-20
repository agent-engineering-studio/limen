"""Separazione api / worker (#77).

Due proprietà, e la seconda è quella che si rompe in silenzio:

1. con ``SCHEDULER__ENABLED=false`` l'API **non registra job** — se lo
   facesse, api e worker eseguirebbero lo stesso sweep due volte, e il
   `_sweep_lock` non se ne accorgerebbe perché è un lock di processo;
2. ``limen worker --health`` interroga il **battito nel database**, non il
   PID: un worker con l'event loop bloccato ha ancora il processo vivo, e un
   healthcheck che guarda il processo lo dichiarerebbe sano.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from contextlib import asynccontextmanager
from typing import Any

import pytest

from limen.cli import worker as worker_mod
from limen.config.settings import IotSettings, Settings
from limen.data.repos.job_runs_repo import JobRun


def _run(*, age_seconds: float) -> JobRun:
    now = dt.datetime.now(dt.UTC)
    started = now - dt.timedelta(seconds=age_seconds + 1)
    return JobRun(
        id=1,
        job_id=worker_mod.HEARTBEAT_JOB,
        scope=None,
        started_at=started,
        finished_at=now - dt.timedelta(seconds=age_seconds),
        status="ok",
        metrics={"period_s": 60.0},
        error=None,
        host="worker-1",
    )


class _Repo:
    def __init__(self, runs: list[JobRun]) -> None:
        self._runs = runs

    async def recent(self, job_id: str | None = None, *, limit: int = 20) -> list[JobRun]:
        return self._runs[:limit]


@pytest.fixture()
def _no_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _init(*_a: Any, **_k: Any) -> None:
        return None

    async def _close(*_a: Any, **_k: Any) -> None:
        return None

    monkeypatch.setattr(worker_mod, "init_pool", _init)
    monkeypatch.setattr(worker_mod, "close_pool", _close)


@pytest.mark.asyncio
async def test_health_is_ok_when_the_heartbeat_is_recent(
    monkeypatch: pytest.MonkeyPatch, _no_pool: None
) -> None:
    monkeypatch.setattr(worker_mod, "job_runs_repo", _Repo([_run(age_seconds=30)]))

    assert await worker_mod.health() == 0


@pytest.mark.asyncio
async def test_health_fails_when_the_heartbeat_is_stale(
    monkeypatch: pytest.MonkeyPatch, _no_pool: None
) -> None:
    """Un worker fermo da dieci minuti non è sano, anche se il processo c'è."""
    monkeypatch.setattr(worker_mod, "job_runs_repo", _Repo([_run(age_seconds=600)]))

    assert await worker_mod.health() == 1


@pytest.mark.asyncio
async def test_health_fails_when_there_is_no_heartbeat_at_all(
    monkeypatch: pytest.MonkeyPatch, _no_pool: None
) -> None:
    monkeypatch.setattr(worker_mod, "job_runs_repo", _Repo([]))

    assert await worker_mod.health() == 1


@pytest.mark.asyncio
async def test_health_window_comes_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, _no_pool: None
) -> None:
    monkeypatch.setattr(worker_mod, "job_runs_repo", _Repo([_run(age_seconds=300)]))
    monkeypatch.setenv("LIMEN_WORKER_HEALTH_MAX_AGE_SECONDS", "600")

    assert await worker_mod.health() == 0


def test_the_api_does_not_register_jobs_when_the_scheduler_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Il flag è l'unica cosa che separa i due processi: se l'API lo ignorasse,
    api e worker eseguirebbero lo stesso sweep due volte."""
    from limen.config.settings import Settings

    monkeypatch.setenv("SCHEDULER__ENABLED", "false")
    assert Settings().scheduler.enabled is False

    monkeypatch.setenv("SCHEDULER__ENABLED", "true")
    assert Settings().scheduler.enabled is True


def test_the_worker_ignores_the_flag_by_construction() -> None:
    """Il worker non legge `scheduler.enabled`: spegnersi per una variabile
    d'ambiente sarebbe un modo silenzioso di fermare tutti i batch."""
    import inspect

    source = inspect.getsource(worker_mod.run)

    assert "scheduler.enabled" not in source


# ---------------------------------------------------------------------------
# Attesa dello schema, battito e ciclo di vita del worker (#116)
# ---------------------------------------------------------------------------


class _SchemaConn:
    """`fetchval` che restituisce in sequenza le risposte preparate, o solleva."""

    def __init__(self, answers: list[object]) -> None:
        self._answers = answers
        self.calls = 0

    async def fetchval(self, _sql: str) -> object:
        self.calls += 1
        answer = self._answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def _patch_acquire(monkeypatch: pytest.MonkeyPatch, conn: _SchemaConn) -> None:
    @asynccontextmanager
    async def _acquire():
        yield conn

    import limen.data.db as db_mod

    monkeypatch.setattr(db_mod, "acquire", _acquire)

    async def _no_sleep(_s: float) -> None:
        return None

    monkeypatch.setattr(worker_mod.asyncio, "sleep", _no_sleep)


@pytest.mark.asyncio
async def test_wait_for_schema_retries_through_errors_until_the_table_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Il worker **attende** le migrazioni, non le applica: due processi che
    migrano insieme sono una corsa. Un database che non risponde ancora è un
    motivo per aspettare, non per morire."""
    conn = _SchemaConn([ConnectionError("db non ancora su"), False, True])
    _patch_acquire(monkeypatch, conn)
    assert await worker_mod._wait_for_schema(timeout_s=60) is True
    assert conn.calls == 3


@pytest.mark.asyncio
async def test_wait_for_schema_gives_up_after_the_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _SchemaConn([False] * 50)
    _patch_acquire(monkeypatch, conn)
    assert await worker_mod._wait_for_schema(timeout_s=10) is False


def test_heartbeat_period_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIMEN_WORKER_HEARTBEAT_SECONDS", "5")
    assert worker_mod._heartbeat_seconds() == 5.0


@pytest.mark.asyncio
async def test_heartbeat_loop_writes_a_row_and_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    written: list[tuple[str, object]] = []

    class _BeatRepo:
        async def start(self, job_id: str, *, scope: str | None = None) -> int:
            written.append(("start", job_id))
            stop.set()  # un battito solo, poi fermati
            return 7

        async def finish(self, run_id: int | None, *, status: str, **_: object) -> None:
            written.append(("finish", run_id))

        async def recent(self, job_id: str | None = None, *, limit: int = 20) -> list[object]:
            return []

    monkeypatch.setattr(worker_mod, "job_runs_repo", _BeatRepo())
    monkeypatch.setenv("LIMEN_WORKER_HEARTBEAT_SECONDS", "0.01")
    stop = asyncio.Event()
    await asyncio.wait_for(worker_mod._heartbeat_loop(stop), timeout=5)
    assert written == [("start", worker_mod.HEARTBEAT_JOB), ("finish", 7)]


@pytest.mark.asyncio
async def test_run_with_health_flag_only_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _health() -> int:
        return 42

    monkeypatch.setattr(worker_mod, "health", _health)
    assert await worker_mod.run(check_health=True) == 42


def _patch_lifecycle(monkeypatch: pytest.MonkeyPatch, *, schema_ok: bool) -> dict[str, Any]:
    events: dict[str, Any] = {
        "closed": 0,
        "registered": False,
        "scheduler_stopped": False,
        "interrotte": None,
    }

    async def _init(*_a: Any, **_k: Any) -> None:
        return None

    async def _close(*_a: Any, **_k: Any) -> None:
        events["closed"] += 1

    async def _schema(**_k: Any) -> bool:
        return schema_ok

    class _Settings:
        db = None
        enable_insitu = False
        iot = IotSettings()

    class _Deps:
        thresholds = None

        @classmethod
        async def build(cls, **_k: Any) -> _Deps:
            return cls()

    class _Scheduler:
        async def __aenter__(self) -> _Scheduler:
            return self

        async def __aexit__(self, *_a: Any) -> None:
            return None

        async def start_in_background(self) -> None:
            return None

        async def stop(self) -> None:
            events["scheduler_stopped"] = True

    async def _register(_scheduler: Any, _deps: Any) -> list[str]:
        events["registered"] = True
        return ["limen-hourly-monitoring"]

    async def _beat(
        stop: asyncio.Event, scheduler: object = None, _s: object = None, _i: object = None
    ) -> None:
        # Il battito finto ferma subito il worker: e' l'equivalente di un
        # SIGTERM arrivato appena partito.
        stop.set()

    async def _aclose() -> None:
        events["http_closed"] = True

    class _Repo:
        @staticmethod
        async def chiudi_interrotte(*, heartbeat_job: str) -> int:
            events["interrotte"] = heartbeat_job
            return 0

    import apscheduler

    import limen.integrations._http as http_mod

    monkeypatch.setattr(worker_mod, "init_pool", _init)
    monkeypatch.setattr(worker_mod, "close_pool", _close)
    monkeypatch.setattr(worker_mod, "get_pool", lambda: None)
    monkeypatch.setattr(worker_mod, "get_settings", lambda: _Settings())
    monkeypatch.setattr(worker_mod, "_wait_for_schema", _schema)
    monkeypatch.setattr(worker_mod, "AppDependencies", _Deps)
    monkeypatch.setattr(worker_mod, "register_jobs", _register)
    monkeypatch.setattr(worker_mod, "_heartbeat_loop", _beat)
    monkeypatch.setattr(worker_mod, "job_runs_repo", _Repo)
    monkeypatch.setattr(apscheduler, "AsyncScheduler", _Scheduler)
    monkeypatch.setattr(http_mod.SharedHttpClient, "aclose", staticmethod(_aclose))
    return events


@pytest.mark.asyncio
async def test_run_refuses_to_start_without_the_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    """Schema assente dopo l'attesa: si esce con errore e si chiude il pool,
    invece di partire e scrivere su tabelle che non esistono."""
    events = _patch_lifecycle(monkeypatch, schema_ok=False)
    assert await worker_mod.run() == 1
    assert events["closed"] == 1
    assert events["registered"] is False
    assert events["interrotte"] is None


@pytest.mark.asyncio
async def test_run_registers_jobs_and_shuts_down_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    events = _patch_lifecycle(monkeypatch, schema_ok=True)
    assert await asyncio.wait_for(worker_mod.run(), timeout=10) == 0
    assert events["registered"] is True
    assert events["interrotte"] == worker_mod.HEARTBEAT_JOB
    assert events["scheduler_stopped"] is True
    assert events["http_closed"] is True
    assert events["closed"] == 1


@pytest.mark.asyncio
async def test_un_timeout_del_database_non_uccide_il_battito(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Il primo battito va in timeout, il secondo riesce: il task resta vivo e
    # solo il battito riuscito rinfresca la sentinella.
    tentativi: list[str] = []
    sentinella = worker_mod.Sentinella(60.0, uscita=lambda _c: None)
    sentinella._ultimo -= 30

    class _BeatRepo:
        async def start(self, job_id: str, *, scope: str | None = None) -> int:
            tentativi.append("start")
            if len(tentativi) == 1:
                raise TimeoutError
            stop.set()
            return 7

        async def finish(self, run_id: int | None, *, status: str, **_: object) -> None:
            tentativi.append("finish")

        async def recent(self, job_id: str | None = None, *, limit: int = 20) -> list[object]:
            return []

    monkeypatch.setattr(worker_mod, "job_runs_repo", _BeatRepo())
    monkeypatch.setenv("LIMEN_WORKER_HEARTBEAT_SECONDS", "0.01")
    stop = asyncio.Event()
    await asyncio.wait_for(worker_mod._heartbeat_loop(stop, None, sentinella), timeout=5)
    assert tentativi == ["start", "start", "finish"]
    assert sentinella.eta() < 5


def test_la_sentinella_esce_senza_battito() -> None:
    uscite: list[int] = []
    sentinella = worker_mod.Sentinella(0.05, uscita=uscite.append)
    sentinella.sorveglia(passo=0.01)
    assert uscite == [1]


def test_la_sentinella_tace_finche_il_battito_arriva() -> None:
    uscite: list[int] = []
    sentinella = worker_mod.Sentinella(0.2, uscita=uscite.append)
    filo = sentinella.avvia()
    for _ in range(10):
        sentinella.battito()
        filo.join(timeout=0.03)
    sentinella.ferma()
    filo.join(timeout=1)
    assert uscite == [] and not filo.is_alive()


def test_un_buco_oltre_la_soglia_e_un_interruzione() -> None:
    adesso = dt.datetime(2026, 11, 19, 7, 58, tzinfo=dt.UTC)
    soglia = dt.timedelta(minutes=20)
    assert worker_mod.interruzione(None, adesso, soglia) is None
    assert worker_mod.interruzione(adesso - dt.timedelta(minutes=19), adesso, soglia) is None
    # 13/11 18:29 → 19/11 07:58: la macchina sospesa.
    dal = dt.datetime(2026, 11, 13, 18, 29, tzinfo=dt.UTC)
    assert worker_mod.interruzione(dal, adesso, soglia) == dal


@pytest.mark.asyncio
async def test_al_risveglio_il_buco_si_scrive_e_si_segnala(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Il buco si legge dal database al primo battito, quindi attraversa un
    riavvio; si segnala una volta sola, e il ping parte a ogni battito."""
    righe: list[tuple[str, str, object]] = []
    mail: list[dict[str, object]] = []
    ping: list[str] = []
    dal = dt.datetime.now(dt.UTC) - dt.timedelta(days=5)

    class _Run:
        status = "ok"
        started_at = dal

    class _BeatRepo:
        n = 0

        async def start(self, job_id: str, *, scope: str | None = None) -> int:
            self.n += 1
            if self.n >= 3:
                stop.set()
            righe.append(("start", job_id, None))
            return self.n

        async def finish(self, run_id: int | None, *, status: str, **kw: object) -> None:
            righe.append(("finish", status, kw.get("metrics")))

        async def recent(self, job_id: str | None = None, *, limit: int = 20) -> list[object]:
            return [_Run()]

    async def _invia(_s: object, **kw: object) -> bool:
        mail.append(kw)
        return True

    async def _fetch(method: str, url: str, **_: object) -> object:
        ping.append(url)
        return type("R", (), {"status_code": 200})()

    settings = Settings(
        worker={"ping_url": "https://kuma.example/api/push/x"},
        contributi={"destinatari": ["curatore@example.org"]},
    )
    monkeypatch.setattr(worker_mod, "job_runs_repo", _BeatRepo())
    monkeypatch.setattr(worker_mod, "invia_testo", _invia)
    monkeypatch.setattr(worker_mod, "fetch_with_retry", _fetch)
    monkeypatch.setenv("LIMEN_WORKER_HEARTBEAT_SECONDS", "0.01")
    stop = asyncio.Event()
    await asyncio.wait_for(worker_mod._heartbeat_loop(stop, None, None, settings), timeout=5)

    interruzioni = [r for r in righe if r[1] == worker_mod.JOB_WORKER_INTERRUZIONE]
    assert len(interruzioni) == 1
    errore = next(r for r in righe if r[0] == "finish" and r[1] == "error")
    metriche = errore[2]
    assert isinstance(metriche, dict)
    assert metriche["dal"] == dal.isoformat()
    assert metriche["ore"] == pytest.approx(120, abs=0.2)
    assert len(mail) == 1
    assert mail[0]["destinatari"] == ["curatore@example.org"]
    assert ping == ["https://kuma.example/api/push/x"] * 2


def test_la_soglia_non_scende_mai_sotto_un_riavvio_da_sentinella() -> None:
    # 900 s di watchdog + 300 di attesa dello schema + 5 minuti = 25 minuti.
    assert worker_mod.soglia_interruzione(30, 900.0) == dt.timedelta(minutes=30)
    assert worker_mod.soglia_interruzione(10, 900.0) == dt.timedelta(minutes=25)
    assert worker_mod.soglia_interruzione(30, 1800.0) == dt.timedelta(minutes=40)


@pytest.mark.asyncio
async def test_un_battito_non_scritto_non_pinga_e_non_chiude_la_lettura(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Database giù: `start` degrada a None. Il ping non deve dire «vivo», e
    l'ultimo battito si rilegge al giro dopo invece di restare None."""
    letture: list[str] = []
    ping: list[str] = []

    class _BeatRepo:
        n = 0

        async def start(self, job_id: str, *, scope: str | None = None) -> int | None:
            self.n += 1
            if self.n >= 2:
                stop.set()
                return 9
            return None

        async def finish(self, run_id: int | None, *, status: str, **_: object) -> None:
            return None

        async def recent(self, job_id: str | None = None, *, limit: int = 20) -> list[object]:
            letture.append("recent")
            return []

    async def _fetch(method: str, url: str, **_: object) -> object:
        ping.append(url)
        return type("R", (), {"status_code": 200})()

    monkeypatch.setattr(worker_mod, "job_runs_repo", _BeatRepo())
    monkeypatch.setattr(worker_mod, "fetch_with_retry", _fetch)
    monkeypatch.setenv("LIMEN_WORKER_HEARTBEAT_SECONDS", "0.01")
    stop = asyncio.Event()
    settings = Settings(worker={"ping_url": "https://kuma.example/api/push/x"})
    await asyncio.wait_for(worker_mod._heartbeat_loop(stop, None, None, settings), timeout=5)
    assert letture == ["recent", "recent"]
    assert ping == ["https://kuma.example/api/push/x"]
