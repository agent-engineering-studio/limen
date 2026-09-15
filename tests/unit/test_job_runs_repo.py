"""`job_runs_repo`: la tracciatura che non può far fallire il job (#116).

La regola del modulo è che ogni funzione degrada a un valore neutro e a una
riga di log: un database irraggiungibile è già un problema, e trasformarlo
anche nella causa per cui lo sweep non gira sarebbe un'aggravante nostra.
Qui si provano entrambi i rami — quello normale con una connessione finta,
quello degradato con una connessione che esplode.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from limen.data.repos import job_runs_repo as repo

T = datetime(2026, 9, 15, 6, tzinfo=UTC)


def _row(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": 1,
        "job_id": "limen-hourly-monitoring",
        "scope": "it-puglia",
        "started_at": T,
        "finished_at": T + timedelta(seconds=90),
        "status": "ok",
        "metrics": '{"cells": 10}',
        "error": None,
        "host": "worker-1",
    }
    base.update(over)
    return base


class _Conn:
    def __init__(self, *, rows: Any = None, row: Any = None, status: str = "") -> None:
        self._rows = rows or []
        self._row = row
        self._status = status
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    async def fetch(self, _sql: str, *_args: Any) -> Any:
        return self._rows

    async def fetchrow(self, _sql: str, *_args: Any) -> Any:
        return self._row

    async def execute(self, sql: str, *args: Any) -> str:
        self.executed.append((sql, args))
        return self._status


def _use(monkeypatch: pytest.MonkeyPatch, conn: _Conn) -> None:
    @asynccontextmanager
    async def _acquire():
        yield conn

    monkeypatch.setattr(repo, "acquire", _acquire)


def _broken(monkeypatch: pytest.MonkeyPatch) -> None:
    @asynccontextmanager
    async def _acquire():
        raise ConnectionError("database giù")
        yield  # pragma: no cover

    monkeypatch.setattr(repo, "acquire", _acquire)


# ---------------------------------------------------------------------------
# JobRun
# ---------------------------------------------------------------------------
def test_duration_comes_from_the_timestamps() -> None:
    run = repo._to_run(_row())
    assert run.duration_s == 90.0
    assert run.metrics == {"cells": 10}  # jsonb arrivato come stringa


def test_a_run_still_running_has_no_duration() -> None:
    """Un processo ucciso a metà lascia la riga `running`: la durata non
    esiste, e inventarne una direbbe il falso."""
    run = repo._to_run(_row(finished_at=None, metrics=None))
    assert run.duration_s is None
    assert run.metrics == {}


def test_hostname_is_readable() -> None:
    assert repo._hostname()


# ---------------------------------------------------------------------------
# Scritture
# ---------------------------------------------------------------------------
async def test_start_returns_the_new_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, _Conn(row={"id": 42}))
    assert await repo.start("limen-x", scope="it-puglia") == 42


async def test_start_degrades_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _broken(monkeypatch)
    assert await repo.start("limen-x") is None


async def test_finish_writes_metrics_as_json(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _Conn()
    _use(monkeypatch, conn)
    await repo.finish(7, status="ok", metrics={"cells": 3, "when": T}, error=None)
    _sql, args = conn.executed[0]
    assert args[0] == 7 and args[1] == "ok"
    # `default=str`: un datetime nelle metriche non deve far saltare la riga.
    assert json.loads(args[2]) == {"cells": 3, "when": str(T)}


async def test_finish_without_an_id_is_a_silent_no_op(monkeypatch: pytest.MonkeyPatch) -> None:
    """Se `start` è degradato, `finish` riceve None e non deve fare niente."""
    conn = _Conn()
    _use(monkeypatch, conn)
    await repo.finish(None, status="ok")
    assert conn.executed == []


async def test_finish_degrades_without_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    _broken(monkeypatch)
    await repo.finish(7, status="error", error="boom")  # nessuna eccezione


# ---------------------------------------------------------------------------
# Letture
# ---------------------------------------------------------------------------
async def test_latest_per_scope_and_its_degradation(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, _Conn(rows=[_row(), _row(id=2, scope="it-molise")]))
    runs = await repo.latest_per_scope("limen-hourly-monitoring")
    assert [r.scope for r in runs] == ["it-puglia", "it-molise"]

    _broken(monkeypatch)
    assert await repo.latest_per_scope("limen-hourly-monitoring") == []


async def test_latest_global_found_missing_and_degraded(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, _Conn(row=_row(scope=None)))
    run = await repo.latest_global("limen-hourly-monitoring")
    assert run is not None and run.scope is None

    _use(monkeypatch, _Conn(row=None))
    assert await repo.latest_global("limen-hourly-monitoring") is None

    _broken(monkeypatch)
    assert await repo.latest_global("limen-hourly-monitoring") is None


async def test_recent_and_its_degradation(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, _Conn(rows=[_row()]))
    assert len(await repo.recent(limit=5)) == 1
    _broken(monkeypatch)
    assert await repo.recent() == []


async def test_finished_since_and_its_degradation(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, _Conn(rows=[_row()]))
    assert len(await repo.finished_since("limen-hourly-monitoring", hours=3)) == 1
    _broken(monkeypatch)
    assert await repo.finished_since("limen-hourly-monitoring", hours=3) == []


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------
async def test_purge_counts_the_deleted_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, _Conn(status="DELETE 12"))
    assert await repo.purge_older_than(90) == 12


async def test_purge_with_nothing_to_delete(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, _Conn(status="DELETE 0"))
    assert await repo.purge_older_than(90) == 0


async def test_purge_degrades_to_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    _broken(monkeypatch)
    assert await repo.purge_older_than(90) == 0
