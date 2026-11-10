"""I fatti del riepilogo sulla qualità dei dati contro un Postgres vero (#421)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from limen.agents.llm_factory.stub import StubChatClient
from limen.cli.qualita_dati import riepilogo
from limen.data.db import acquire
from limen.data.repos import qualita_dati_repo

pytestmark = pytest.mark.integration

ORA = datetime.now(UTC).replace(microsecond=0)


async def _run(
    job: str, scope: str | None, fine: datetime, status: str = "ok", err: str | None = None
) -> None:
    async with acquire() as conn:
        await conn.execute(
            "INSERT INTO job_runs (job_id, scope, started_at, finished_at, status, error, host)"
            " VALUES ($1, $2, $3, $3, $4, $5, 'test')",
            job,
            scope,
            fine,
            status,
            err,
        )


async def test_fatti_e_report(
    reset_db: None, pg_pool: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LIMEN_REPORTS_DIR", str(tmp_path))
    async with acquire() as conn:
        await conn.execute("DELETE FROM job_runs")
    # Orario, fermo da 5 ore.
    for h in range(5, 30):
        await _run("limen-test-orario", None, ORA - timedelta(hours=h))
    # Notturno puntuale.
    for d in range(1, 8):
        await _run("limen-test-notte", "passo", ORA - timedelta(days=d) + timedelta(hours=2))
    await _run("limen-test-notte", "passo", ORA - timedelta(hours=1), "error", "x?key=segreta")
    # La settimana prima: un riepilogo con l'alluvione all'1 %.
    async with acquire() as conn:
        await conn.execute(
            "INSERT INTO job_runs (job_id, scope, started_at, finished_at, status, metrics, host)"
            " VALUES ($1, $2, $3, $3, 'ok', $4::jsonb, 'test')",
            qualita_dati_repo.JOB,
            qualita_dati_repo.SCOPE,
            ORA - timedelta(days=7),
            '{"non_misurate": {"flood": 0.01}}',
        )

    fatti = await qualita_dati_repo.raccogli(ORA)
    assert [r.job_id for r in fatti.ritardi()] == ["limen-test-orario"]
    (errore,) = fatti.errori
    assert errore.messaggio == "x?key=<nascosto>"
    prima = await qualita_dati_repo.settimana_prima(ORA)
    assert prima == {"non_misurate": {"flood": 0.01}}

    paragrafo = "Il job limen-test-orario è fermo da 5 h: è il guasto da guardare per primo."
    metriche = await riepilogo(ORA, StubChatClient(canned_responses=[paragrafo]))
    assert metriche["in_ritardo"] == ["limen-test-orario"]
    assert metriche["problemi"] == 2
    assert metriche["ai"] is True
    testo = (tmp_path / f"qualita_dati_{ORA:%Y-%m-%d}.md").read_text(encoding="utf-8")
    assert "**limen-test-orario** è fermo" in testo
    assert testo.index(paragrafo) < testo.index("**limen-test-orario** è fermo")
    assert "segreta" not in testo
