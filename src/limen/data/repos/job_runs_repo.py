"""Tracciatura dei job periodici (#75).

Quattro letture e due scritture. asyncpg puro, nessun ORM, come il resto del
layer dati.

La regola che governa questo modulo: **la tracciatura non può far fallire il
job**. Un database irraggiungibile è già un problema; trasformarlo anche nella
causa per cui lo sweep nazionale non gira sarebbe un'aggravante nostra, non
del database. Ogni funzione degrada a un valore neutro e a una riga di log.
"""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from limen.core.logging import get_logger
from limen.data.db import acquire

log = get_logger(__name__)

#: Stati ammessi, come nel CHECK della migrazione. `skipped` non è un errore:
#: lo sweep che trova il lock occupato salta il tick di proposito.
Status = str


@dataclass(frozen=True, slots=True)
class JobRun:
    id: int
    job_id: str
    scope: str | None
    started_at: datetime
    finished_at: datetime | None
    status: str
    metrics: dict[str, Any]
    error: str | None
    host: str

    @property
    def duration_s(self) -> float | None:
        """Durata dalla riga, non dalle metriche.

        `metrics.duration_s` la scrive il tracciatore, ma una riga rimasta
        `running` — processo ucciso a metà — non ce l'ha, e per quelle la
        differenza fra i due timestamp è l'unica cosa disponibile.
        """
        if self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds()


def _hostname() -> str:
    """Nome del processo che scrive. Distingue `api` da `worker` (#77)."""
    try:
        return socket.gethostname()
    except OSError:  # pragma: no cover — hostname indisponibile è teorico
        return "unknown"


def _to_run(row: Any) -> JobRun:
    metrics = row["metrics"]
    if isinstance(metrics, str):
        metrics = json.loads(metrics)
    return JobRun(
        id=int(row["id"]),
        job_id=str(row["job_id"]),
        scope=row["scope"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        status=str(row["status"]),
        metrics=metrics or {},
        error=row["error"],
        host=str(row["host"]),
    )


async def start(job_id: str, *, scope: str | None = None) -> int | None:
    """Apre la riga di un run. ``None`` se la tracciatura non è disponibile."""
    try:
        async with acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO job_runs (job_id, scope, host) VALUES ($1, $2, $3) RETURNING id",
                job_id,
                scope,
                _hostname(),
            )
    except Exception as exc:
        log.warning("job_runs.degraded", phase="start", job=job_id, error=str(exc))
        return None
    return int(row["id"]) if row is not None else None


async def finish(
    run_id: int | None,
    *,
    status: str,
    metrics: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    """Chiude la riga. Con ``run_id`` a ``None`` è un no-op silenzioso."""
    if run_id is None:
        return
    try:
        async with acquire() as conn:
            await conn.execute(
                "UPDATE job_runs SET finished_at = now(), status = $2, "
                "metrics = $3::jsonb, error = $4 WHERE id = $1",
                run_id,
                status,
                json.dumps(metrics or {}, default=str),
                error,
            )
    except Exception as exc:
        log.warning("job_runs.degraded", phase="finish", run_id=run_id, error=str(exc))


async def latest_per_scope(job_id: str) -> list[JobRun]:
    """L'ultimo run **concluso** per ogni scope di un job.

    Concluso e non semplicemente l'ultimo: una riga `running` non ha una
    durata, e "aggiornato alle" letto da un run in corso mostrerebbe l'ora in
    cui il calcolo è cominciato come se fosse quella del dato.
    """
    try:
        async with acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT ON (scope)
                       id, job_id, scope, started_at, finished_at, status,
                       metrics, error, host
                FROM job_runs
                WHERE job_id = $1 AND scope IS NOT NULL AND finished_at IS NOT NULL
                ORDER BY scope, started_at DESC
                """,
                job_id,
            )
    except Exception as exc:
        log.warning("job_runs.degraded", phase="latest_per_scope", error=str(exc))
        return []
    return [_to_run(r) for r in rows]


async def latest_global(job_id: str) -> JobRun | None:
    """L'ultimo run senza scope di un job — lo sweep nel suo insieme."""
    try:
        async with acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, job_id, scope, started_at, finished_at, status,
                       metrics, error, host
                FROM job_runs
                WHERE job_id = $1 AND scope IS NULL
                ORDER BY started_at DESC
                LIMIT 1
                """,
                job_id,
            )
    except Exception as exc:
        log.warning("job_runs.degraded", phase="latest_global", error=str(exc))
        return None
    return _to_run(row) if row is not None else None


async def recent(job_id: str | None = None, *, limit: int = 20) -> list[JobRun]:
    """Gli ultimi run, di un job o di tutti."""
    try:
        async with acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, job_id, scope, started_at, finished_at, status,
                       metrics, error, host
                FROM job_runs
                WHERE ($1::text IS NULL OR job_id = $1)
                ORDER BY started_at DESC, id DESC
                LIMIT $2
                """,
                job_id,
                limit,
            )
    except Exception as exc:
        log.warning("job_runs.degraded", phase="recent", error=str(exc))
        return []
    return [_to_run(r) for r in rows]


async def finished_since(job_id: str, *, hours: int, limit: int = 500) -> list[JobRun]:
    """I run **con scope** di un job conclusi nelle ultime ``hours``, dal più recente.

    Con scope: il briefing asincrono (#78) lavora per regione, e la riga
    globale dello sweep non ne nomina nessuna. Il filtro fine — quali regioni
    meritano una narrativa — lo fa il chiamante sulle metriche, perché è una
    regola di prodotto (`briefing_min_level`) e non una query.
    """
    try:
        async with acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, job_id, scope, started_at, finished_at, status,
                       metrics, error, host
                FROM job_runs
                WHERE job_id = $1
                  AND scope IS NOT NULL
                  AND finished_at IS NOT NULL
                  AND finished_at >= now() - $2::int * interval '1 hour'
                ORDER BY finished_at DESC
                LIMIT $3
                """,
                job_id,
                hours,
                limit,
            )
    except Exception as exc:
        log.warning("job_runs.degraded", phase="finished_since", job=job_id, error=str(exc))
        return []
    return [_to_run(r) for r in rows]


async def purge_older_than(days: int) -> int:
    """Retention. Un DELETE e non un DROP PARTITION: `job_runs` cresce di
    poche migliaia di righe al giorno, non dei gigabyte delle tabelle calde."""
    try:
        async with acquire() as conn:
            status = await conn.execute(
                "DELETE FROM job_runs WHERE started_at < now() - $1::int * interval '1 day'",
                days,
            )
    except Exception as exc:
        log.warning("job_runs.degraded", phase="purge", error=str(exc))
        return 0
    removed = int(status.split()[-1]) if status else 0
    if removed:
        log.info("job_runs.purged", rows=removed, older_than_days=days)
    return removed


__all__ = [
    "JobRun",
    "Status",
    "finish",
    "finished_since",
    "latest_global",
    "latest_per_scope",
    "purge_older_than",
    "recent",
    "start",
]
