"""La pipeline notturna: sei passi, e uno che cade non porta giù gli altri (#78).

È la proprietà per cui esiste un job unico invece di sei schedule: prima un
drift che esplodeva non impediva alle partizioni di girare solo perché erano
job diversi. Ora sono lo stesso job, quindi l'isolamento va scritto — e
provato — invece che ereditato dallo scheduler.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

import limen.api.jobs.nightly as nightly
from limen.api.jobs.nightly import STEPS, run_nightly_pipeline
from limen.config.settings import ScoringMode
from limen.core.models.hazard import HazardType


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


# ---------------------------------------------------------------------------
# Passo shadow e retrain (#116)
# ---------------------------------------------------------------------------


def _shadow_deps(*, mode: ScoringMode, hazards: list[HazardType], fail_build: bool = False) -> Any:
    class _Scoring:
        pass

    class _Hazards:
        enabled = hazards

    class _Scheduler:
        sweep_concurrency = 2

    class _Settings:
        scoring = _Scoring()
        scheduler = _Scheduler()
        enable_insitu = False

    _Settings.scoring.mode = mode
    _Settings.hazards = _Hazards()

    class _Result:
        def __init__(self, n: int) -> None:
            class _Ctx:
                cell_results = [object()] * n

            self.context = _Ctx()

    class _Workflow:
        async def run(self, ctx: Any) -> _Result:
            if ctx.aoi_id == "it-rotta":
                raise RuntimeError("regione esplosa")
            return _Result(4)

    class _Deps:
        settings = _Settings()

        def build_workflow(self, *, hazard: HazardType, profile: str) -> _Workflow:
            assert profile == "nightly"
            if fail_build and hazard is HazardType.FLOOD:
                raise RuntimeError("pericolo non valutabile")
            return _Workflow()

    return _Deps()


@pytest.mark.asyncio
async def test_shadow_is_skipped_outside_shadow_mode() -> None:
    deps = _shadow_deps(mode=ScoringMode.CHAMPION_ONLY, hazards=[HazardType.LANDSLIDE])
    out = await nightly._shadow_ml(deps)
    assert out["status"] == "skipped"


@pytest.mark.asyncio
async def test_shadow_without_aois_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _none() -> list[str]:
        return []

    monkeypatch.setattr(nightly, "_all_aois", _none)
    deps = _shadow_deps(mode=ScoringMode.SHADOW, hazards=[HazardType.LANDSLIDE])
    assert (await nightly._shadow_ml(deps))["reason"] == "no aoi"


@pytest.mark.asyncio
async def test_shadow_scores_every_aoi_and_isolates_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Una regione che esplode e un pericolo non valutabile non fermano le
    altre: il notturno misura quello che può."""

    async def _aois() -> list[str]:
        return ["it-puglia", "it-rotta"]

    monkeypatch.setattr(nightly, "_all_aois", _aois)
    deps = _shadow_deps(
        mode=ScoringMode.SHADOW,
        hazards=[HazardType.LANDSLIDE, HazardType.FLOOD],
        fail_build=True,
    )
    out = await nightly._shadow_ml(deps)
    assert out == {"aois": 1, "cells": 4}


def _retrain_deps(*, auto: bool, timeout: int = 60) -> Any:
    class _Training:
        auto_retrain = auto
        optuna_timeout_seconds = timeout

    class _Settings:
        training = _Training()

    class _Deps:
        settings = _Settings()

    return _Deps()


class _Proc:
    def __init__(self, *, returncode: int, stderr: bytes = b"", hang: bool = False) -> None:
        self.returncode = returncode
        self._stderr = stderr
        self._hang = hang
        self.killed = False

    async def communicate(self) -> tuple[bytes, bytes]:
        if self._hang:
            await asyncio.sleep(3600)
        return b"", self._stderr

    def kill(self) -> None:
        self.killed = True

    async def wait(self) -> int:
        return self.returncode


def _spawn(monkeypatch: pytest.MonkeyPatch, proc: _Proc) -> list[tuple[str, ...]]:
    launched: list[tuple[str, ...]] = []

    async def _exec(*args: str, **_kw: Any) -> _Proc:
        launched.append(args)
        return proc

    monkeypatch.setattr(nightly.asyncio, "create_subprocess_exec", _exec)
    return launched


@pytest.mark.asyncio
async def test_retrain_runs_limen_train_in_a_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sottoprocesso e non chiamata diretta: Optuna col suo carico non deve
    restare nella memoria del worker per lo sweep del mattino."""
    launched = _spawn(monkeypatch, _Proc(returncode=0))
    out = await nightly._retrain(_retrain_deps(auto=True), triggered=True)
    assert out == {"returncode": 0}
    assert launched == [("uv", "run", "limen", "train")]


@pytest.mark.asyncio
async def test_retrain_reports_a_failed_training(monkeypatch: pytest.MonkeyPatch) -> None:
    _spawn(monkeypatch, _Proc(returncode=2, stderr=b"Optuna: nessun trial valido"))
    out = await nightly._retrain(_retrain_deps(auto=True), triggered=True)
    assert out["status"] == "error"
    assert out["returncode"] == 2
    assert "nessun trial valido" in out["stderr"]


@pytest.mark.asyncio
async def test_retrain_kills_a_hung_training(monkeypatch: pytest.MonkeyPatch) -> None:
    """Oltre il budget non è lento, è bloccato: una notte appesa a un training
    non finisce mai."""
    proc = _Proc(returncode=-9, hang=True)
    _spawn(monkeypatch, proc)

    real_wait_for = asyncio.wait_for

    async def _short(awaitable: Any, timeout: float) -> Any:
        return await real_wait_for(awaitable, timeout=0.01)

    monkeypatch.setattr(nightly.asyncio, "wait_for", _short)
    out = await nightly._retrain(_retrain_deps(auto=True, timeout=10), triggered=True)
    assert out["status"] == "error"
    assert "timed out" in out["reason"]
    assert proc.killed is True
