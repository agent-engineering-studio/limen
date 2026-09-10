"""``limen jobs`` — cosa ha girato, quando, e quanto è durato (#75).

Legge `job_runs`. Prima di questa tabella la stessa domanda si rispondeva
leggendo i log del container, cioè non si rispondeva.

Output su log strutturato e non `print`: è la regola del progetto e qui non
fa eccezione — una riga per run, come fa `limen shadow-report`. Chi vuole una
tabella la ottiene dal JSON dei log, che è più utile di un ASCII allineato.

Env:

* ``LIMEN_JOBS_JOB``     — filtra su un job (es. ``limen-hourly-monitoring``).
* ``LIMEN_JOBS_PER_AOI`` — ``1`` per l'ultimo run di **ogni regione** invece
  degli ultimi N globali: è la vista che serve per sapere quale regione fa
  durare lo sweep.
* ``LIMEN_JOBS_LIMIT``   — quanti run (default 20).
"""

from __future__ import annotations

import os

from limen.core.logging import get_logger
from limen.data.db import lifespan_pool
from limen.data.repos import job_runs_repo
from limen.data.repos.job_runs_repo import JobRun

log = get_logger(__name__)


def _row(run: JobRun) -> dict[str, object]:
    return {
        "job": run.job_id,
        "scope": run.scope or "-",
        "status": run.status,
        "started": run.started_at.isoformat(timespec="seconds"),
        "duration_s": run.duration_s,
        "host": run.host,
        **({"error": run.error} if run.error else {}),
        **{k: v for k, v in run.metrics.items() if k != "duration_s"},
    }


async def run() -> int:
    job = os.getenv("LIMEN_JOBS_JOB", "").strip() or None
    per_aoi = os.getenv("LIMEN_JOBS_PER_AOI", "").strip() in {"1", "true", "yes"}
    limit = int(os.getenv("LIMEN_JOBS_LIMIT", "20"))

    async with lifespan_pool():
        if per_aoi:
            if job is None:
                log.error("jobs.per_aoi_needs_job", hint="imposta LIMEN_JOBS_JOB")
                return 2
            runs = await job_runs_repo.latest_per_scope(job)
            # Ordinate per durata decrescente: la prima riga è la regione che
            # fa durare lo sweep, che è la domanda per cui esiste il comando.
            runs.sort(key=lambda r: r.duration_s or 0.0, reverse=True)
        else:
            runs = await job_runs_repo.recent(job, limit=limit)

    if not runs:
        log.info("jobs.empty", job=job, per_aoi=per_aoi)
        return 0
    for item in runs:
        log.info("jobs.row", **_row(item))
    total = sum(r.duration_s or 0.0 for r in runs)
    log.info(
        "jobs.summary",
        runs=len(runs),
        total_duration_s=round(total, 1),
        slowest=runs[0].scope or runs[0].job_id if per_aoi else None,
    )
    return 0


def main() -> int:
    import asyncio

    return asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
