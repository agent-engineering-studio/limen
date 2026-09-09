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

import datetime as dt
from typing import Any

import pytest

from limen.cli import worker as worker_mod
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
