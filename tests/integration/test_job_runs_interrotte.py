"""`chiudi_interrotte` contro un PostgreSQL vero: chi si chiude e chi no.

I test unitari sostituiscono la connessione e non vedono la query; qui si
prova la regola che la query porta — solo le righe `running` di un host che
ha scritto il battito, mai quelle di chi chiama né di un processo che il
battito non lo scrive (MCP, CLI).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from limen.data.db import acquire
from limen.data.repos import job_runs_repo

pytestmark = pytest.mark.integration

_BATTITO = "limen-worker-heartbeat"
_T = datetime(2026, 10, 11, 21, tzinfo=UTC)


async def _riga(
    job_id: str,
    host: str,
    *,
    status: str,
    started: datetime,
    finished: datetime | None = None,
) -> int:
    async with acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO job_runs (job_id, host, status, started_at, finished_at) "
            "VALUES ($1, $2, $3, $4, $5) RETURNING id",
            job_id,
            host,
            status,
            started,
            finished,
        )
    assert row is not None
    return int(row["id"])


async def test_chiude_solo_le_corse_dei_worker_morti(
    pg_pool: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with acquire() as conn:
        await conn.execute("DELETE FROM job_runs")
    monkeypatch.setattr(job_runs_repo, "_hostname", lambda: "worker-nuovo")

    await _riga(_BATTITO, "worker-vecchio", status="ok", started=_T, finished=_T)
    ultima = _T + timedelta(minutes=11)
    await _riga("limen-alert-digest", "worker-vecchio", status="ok", started=_T, finished=ultima)
    interrotta = await _riga(
        "limen-fedelta-racconti", "worker-vecchio", status="running", started=_T
    )
    await _riga(_BATTITO, "worker-nuovo", status="ok", started=_T, finished=_T)
    mia = await _riga("limen-hourly-monitoring", "worker-nuovo", status="running", started=_T)
    mcp = await _riga("limen-hourly-monitoring", "mcp-1", status="running", started=_T)

    assert await job_runs_repo.chiudi_interrotte(heartbeat_job=_BATTITO) == 1

    async with acquire() as conn:
        righe = {
            r["id"]: r
            for r in await conn.fetch("SELECT id, status, finished_at, error FROM job_runs")
        }
    assert righe[interrotta]["status"] == "error"
    assert righe[interrotta]["finished_at"] == ultima
    assert "worker-vecchio" in righe[interrotta]["error"]
    assert righe[mia]["status"] == "running"
    assert righe[mcp]["status"] == "running"

    # Rilanciabile: una seconda volta non trova più niente.
    assert await job_runs_repo.chiudi_interrotte(heartbeat_job=_BATTITO) == 0
