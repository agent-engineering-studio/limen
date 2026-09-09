"""Tracciatura dei job periodici: un context manager, nient'altro (#75).

Avvolge un job e scrive una riga in `job_runs` con inizio, fine, esito e
metriche. Il valore sta in tre proprietà che è facile sbagliare:

* **L'eccezione viene rilanciata dopo la scrittura.** Registrare l'errore e
  poi inghiottirlo trasformerebbe questo modulo in un `except: pass`
  distribuito: lo scheduler non saprebbe che il job è fallito e non
  ritenterebbe.
* **La tracciatura non può far fallire il job.** Il repo degrada già a valori
  neutri; qui il context manager non solleva nulla di suo.
* **Le metriche si riempiono dall'interno.** Il chiamante riceve un dizionario
  mutabile e ci scrive quello che sa (celle, righe, secondi): un decoratore
  che le indovinasse dall'esterno saprebbe solo la durata.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, MutableMapping
from contextlib import asynccontextmanager
from typing import Any

from limen.core.logging import get_logger
from limen.data.repos import job_runs_repo

log = get_logger(__name__)


@asynccontextmanager
async def tracked(
    job_id: str, *, scope: str | None = None
) -> AsyncIterator[MutableMapping[str, Any]]:
    """Apre e chiude una riga di `job_runs` attorno a un blocco.

    Uso::

        async with tracked("limen-hourly-monitoring") as metrics:
            metrics["aois"] = len(aois)

    Un blocco che vuole registrarsi come **salto** e non come successo scrive
    ``metrics["status"] = "skipped"``: è il caso del tick che trova il lock
    occupato, che non è un errore ma non è nemmeno un lavoro svolto.
    """
    run_id = await job_runs_repo.start(job_id, scope=scope)
    metrics: dict[str, Any] = {}
    t0 = time.perf_counter()
    try:
        yield metrics
    except Exception as exc:
        metrics["duration_s"] = round(time.perf_counter() - t0, 3)
        await job_runs_repo.finish(
            run_id,
            status="error",
            metrics=metrics,
            error=f"{type(exc).__name__}: {exc}",
        )
        log.error(
            "job.failed",
            job=job_id,
            scope=scope,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        raise
    metrics["duration_s"] = round(time.perf_counter() - t0, 3)
    status = str(metrics.pop("status", "ok"))
    await job_runs_repo.finish(run_id, status=status, metrics=metrics)
    log.info("job.done", job=job_id, scope=scope, status=status, **metrics)


def track_job(job_id: str) -> Any:
    """Avvolge la callable di un job perché lo scheduler la registri.

    Serve in `registration.py`: avvolgere lì significa un punto unico invece
    di quattordici moduli da modificare, e un job nuovo che si dimentica di
    tracciarsi diventa impossibile — la registrazione è l'unica strada per
    entrare nello scheduler.
    """

    def wrap(fn: Any) -> Any:
        async def runner(*args: Any, **kwargs: Any) -> Any:
            async with tracked(job_id) as metrics:
                out = await fn(*args, **kwargs)
                # Un job che ritorna un dizionario di conteggi lo racconta da
                # sé: `{aoi: celle}` diventa `aois` e `cells` senza che il job
                # debba sapere che esiste `job_runs`.
                if isinstance(out, dict) and out:
                    numeric = [v for v in out.values() if isinstance(v, (int, float))]
                    if len(numeric) == len(out):
                        metrics["scopes"] = len(out)
                        metrics["total"] = sum(numeric)
                elif isinstance(out, int):
                    metrics["total"] = out
                return out

        runner.__name__ = getattr(fn, "__name__", "job")
        runner.__qualname__ = getattr(fn, "__qualname__", runner.__name__)
        return runner

    return wrap


__all__ = ["track_job", "tracked"]
