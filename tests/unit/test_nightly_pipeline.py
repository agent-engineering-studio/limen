"""La pipeline notturna: sei passi, e uno che cade non porta giù gli altri (#78).

È la proprietà per cui esiste un job unico invece di sei schedule: prima un
drift che esplodeva non impediva alle partizioni di girare solo perché erano
job diversi. Ora sono lo stesso job, quindi l'isolamento va scritto — e
provato — invece che ereditato dallo scheduler.
"""

from __future__ import annotations

from typing import Any

import pytest

import limen.api.jobs.nightly as nightly
from limen.api.jobs.nightly import STEPS, run_nightly_pipeline


class _Recorder:
    """Il repo di tracciatura, sostituito: registra invece di scrivere."""

    def __init__(self) -> None:
        self.finished: list[tuple[str | None, str]] = []
        self._next = 1

    async def start(self, job_id: str, *, scope: str | None = None) -> int | None:
        self._next += 1
        self._scope = scope
        return self._next

    async def finish(
        self,
        run_id: int | None,
        *,
        status: str,
        metrics: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        self.finished.append((self._scope, status))


@pytest.fixture()
def recorder(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    import limen.api.jobs._tracking as tracking

    rec = _Recorder()
    monkeypatch.setattr(tracking, "job_runs_repo", rec)
    return rec


@pytest.fixture()
def stubbed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ogni passo ridotto a un valore: qui si prova l'orchestrazione."""

    async def shadow(_deps: object) -> dict[str, Any]:
        return {"aois": 2, "cells": 20}

    async def drift(_deps: object) -> int:
        return 1

    async def forecast(_deps: object) -> int:
        return 7

    async def partitions(_deps: object) -> dict[str, int]:
        return {"risk_assessments": 1}

    async def cache(_deps: object) -> int:
        return 3

    monkeypatch.setattr(nightly, "_shadow_ml", shadow)
    monkeypatch.setattr(nightly, "run_drift_monitor_job", drift)
    monkeypatch.setattr(nightly, "run_forecast_history_job", forecast)
    monkeypatch.setattr(nightly, "run_partitions_job", partitions)
    monkeypatch.setattr(nightly, "run_cache_cleanup_job", cache)


def _deps() -> Any:
    from limen.config.settings import Settings

    class _Deps:
        settings = Settings.model_validate({"scheduler": {"cache_cleanup": "apscheduler"}})

    return _Deps()


@pytest.mark.asyncio
@pytest.mark.usefixtures("stubbed")
async def test_every_step_gets_its_own_tracked_row(recorder: _Recorder) -> None:
    out = await run_nightly_pipeline(_deps())
    assert list(out) == list(STEPS)
    assert [scope for scope, _ in recorder.finished] == list(STEPS)
    assert {status for _, status in recorder.finished} <= {"ok", "skipped"}


@pytest.mark.asyncio
@pytest.mark.usefixtures("stubbed")
async def test_a_failing_step_does_not_stop_the_ones_after_it(
    recorder: _Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un drift che esplode non deve impedire alle partizioni di domani di
    esistere: senza partizione, ogni scrittura finisce in `*_default`, dove la
    retention non arriva."""

    async def boom(_deps: object) -> int:
        raise RuntimeError("drift exploded")

    monkeypatch.setattr(nightly, "run_drift_monitor_job", boom)

    out = await run_nightly_pipeline(_deps())

    assert out["drift_monitor"] is None
    assert out["partitions_maintain"] == {"dropped": {"risk_assessments": 1}}
    assert out["retention"] == {"cache_rows": 3}
    by_scope = dict(recorder.finished)
    assert by_scope["drift_monitor"] == "error"
    assert by_scope["partitions_maintain"] == "ok"


@pytest.mark.asyncio
@pytest.mark.usefixtures("stubbed")
async def test_retrain_only_runs_when_the_drift_asked_and_the_operator_allowed(
    monkeypatch: pytest.MonkeyPatch,
    recorder: _Recorder,
) -> None:
    """`TRAINING__AUTO_RETRAIN` è false di default: addestrare da soli è
    accettabile, ma finché nessuno ha acceso l'interruttore un retrain
    notturno è solo Optuna che si prende la macchina."""
    launched: list[tuple[str, ...]] = []

    async def never(*args: str, **_kwargs: Any) -> Any:
        launched.append(args)
        raise AssertionError("il sottoprocesso non doveva partire")

    monkeypatch.setattr(nightly.asyncio, "create_subprocess_exec", never)

    out = await run_nightly_pipeline(_deps())

    assert out["drift_monitor"] == {"triggered": True}
    assert out["retrain"] == {
        "status": "skipped",
        "reason": "TRAINING__AUTO_RETRAIN is false",
    }
    assert launched == []


@pytest.mark.asyncio
@pytest.mark.usefixtures("stubbed", "recorder")
async def test_retention_is_skipped_under_the_pg_cron_backend() -> None:
    """`SCHEDULER__CACHE_CLEANUP` continua a dire *chi* purga; il notturno
    cambia solo *quando* lo fa il worker."""
    from limen.config.settings import Settings

    class _Deps:
        settings = Settings.model_validate({"scheduler": {"cache_cleanup": "pg_cron"}})

    out = await run_nightly_pipeline(_Deps())
    assert out["retention"] == {
        "status": "skipped",
        "reason": "cache cleanup runs under pg_cron",
    }
