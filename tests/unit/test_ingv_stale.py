"""Il job INGV acceso ma fermo si dice (#287).

Senza righe in `seismic_pga_cella` la componente E vale zero, ed è giusto solo
se il job gira: fermo, lo zero è un «nessuna scossa» che nessuno ha misurato.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import structlog

from limen.agents.executors import seismic_check
from limen.api.jobs.ids import JOB_INGV_SYNC
from limen.config.settings import SchedulerSettings


def test_l_id_del_job_e_lo_stesso_del_registro() -> None:
    assert seismic_check.JOB_INGV_SYNC == JOB_INGV_SYNC


class _Settings:
    def __init__(self, scheduler: SchedulerSettings) -> None:
        self.scheduler = scheduler


@pytest.mark.parametrize(
    ("acceso", "ultimo", "avvisa"),
    [
        (True, None, True),
        (True, timedelta(hours=5), True),
        (True, timedelta(minutes=30), False),
        (False, None, False),
    ],
    ids=["mai_girato", "fermo", "recente", "spento"],
)
async def test_avviso_ingv_stale(
    monkeypatch: pytest.MonkeyPatch, acceso: bool, ultimo: timedelta | None, avvisa: bool
) -> None:
    monkeypatch.setattr(
        seismic_check,
        "get_settings",
        lambda: _Settings(SchedulerSettings(enable_ingv_sync=acceso)),
    )

    async def ultimo_riuscito(job_id: str) -> datetime | None:
        assert job_id == JOB_INGV_SYNC
        return None if ultimo is None else datetime.now(UTC) - ultimo

    monkeypatch.setattr(seismic_check.job_runs_repo, "ultimo_riuscito", ultimo_riuscito)
    with structlog.testing.capture_logs() as logs:
        await seismic_check._avvisa_se_fermo()
    stale = [e for e in logs if e.get("label") == "ingv.stale"]
    assert bool(stale) is avvisa
    if avvisa:
        assert stale[0]["event"] == "integration.degraded"
