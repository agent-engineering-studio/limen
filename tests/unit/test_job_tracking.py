"""Tracciatura dei job: le tre proprietà che è facile sbagliare (#75).

1. **L'eccezione viene rilanciata dopo la scrittura.** Registrare l'errore e
   poi inghiottirlo trasformerebbe il tracciatore in un `except: pass`
   distribuito: lo scheduler non saprebbe che il job è fallito.
2. **La tracciatura non può far fallire il job.** Un database irraggiungibile
   è già un problema; diventare anche la causa per cui lo sweep non gira
   sarebbe un'aggravante nostra.
3. **`skipped` non è `error`.** Lo sweep che trova il lock occupato salta di
   proposito: contarlo fra gli errori renderebbe illeggibile il tasso di
   errore, non contarlo nasconderebbe che il sistema è in ritardo su se stesso.
"""

from __future__ import annotations

from typing import Any

import pytest

from limen.api.jobs._tracking import track_job, tracked


class _Recorder:
    """Sostituisce il repo: registra le chiamate invece di scrivere."""

    def __init__(self, *, start_fails: bool = False, finish_fails: bool = False) -> None:
        self.started: list[tuple[str, str | None]] = []
        self.finished: list[dict[str, Any]] = []
        self._start_fails = start_fails
        self._finish_fails = finish_fails
        self._next_id = 1

    async def start(self, job_id: str, *, scope: str | None = None) -> int | None:
        self.started.append((job_id, scope))
        if self._start_fails:
            # Il repo vero degrada già a None; qui si prova che il context
            # manager sopravvive a un run_id assente.
            return None
        run_id = self._next_id
        self._next_id += 1
        return run_id

    async def finish(
        self,
        run_id: int | None,
        *,
        status: str,
        metrics: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        if self._finish_fails:
            raise RuntimeError("db down")
        self.finished.append(
            {"run_id": run_id, "status": status, "metrics": metrics or {}, "error": error}
        )


@pytest.fixture()
def repo(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    rec = _Recorder()
    import limen.api.jobs._tracking as mod

    monkeypatch.setattr(mod, "job_runs_repo", rec)
    return rec


@pytest.mark.asyncio
async def test_a_successful_block_is_recorded_ok_with_its_metrics(repo: _Recorder) -> None:
    async with tracked("limen-test", scope="it-puglia") as metrics:
        metrics["cells"] = 42

    assert repo.started == [("limen-test", "it-puglia")]
    assert repo.finished[0]["status"] == "ok"
    assert repo.finished[0]["metrics"]["cells"] == 42
    assert repo.finished[0]["metrics"]["duration_s"] >= 0.0


@pytest.mark.asyncio
async def test_an_exception_is_recorded_and_then_re_raised(repo: _Recorder) -> None:
    with pytest.raises(ValueError, match="boom"):
        async with tracked("limen-test"):
            raise ValueError("boom")

    assert repo.finished[0]["status"] == "error"
    assert repo.finished[0]["error"] == "ValueError: boom"
    # La durata c'è anche in errore: quanto ha girato prima di rompersi è
    # metà della diagnosi.
    assert repo.finished[0]["metrics"]["duration_s"] >= 0.0


@pytest.mark.asyncio
async def test_a_skipped_block_is_not_an_error(repo: _Recorder) -> None:
    async with tracked("limen-test") as metrics:
        metrics["status"] = "skipped"
        metrics["reason"] = "previous sweep still running"

    assert repo.finished[0]["status"] == "skipped"
    assert repo.finished[0]["metrics"]["reason"] == "previous sweep still running"
    # `status` non resta fra le metriche: è una colonna, non una metrica.
    assert "status" not in repo.finished[0]["metrics"]


@pytest.mark.asyncio
async def test_tracking_that_cannot_start_does_not_stop_the_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rec = _Recorder(start_fails=True)
    import limen.api.jobs._tracking as mod

    monkeypatch.setattr(mod, "job_runs_repo", rec)

    ran = False
    async with tracked("limen-test"):
        ran = True

    assert ran, "il blocco deve girare anche senza tracciatura"


@pytest.mark.asyncio
async def test_a_wrapped_job_summarises_its_own_return_value(repo: _Recorder) -> None:
    """Un job che ritorna `{scope: conteggio}` si racconta da sé, senza
    sapere che `job_runs` esiste."""

    async def job(_deps: object) -> dict[str, int]:
        return {"it-puglia": 100, "it-basilicata": 50}

    out = await track_job("limen-test")(job)(object())

    assert out == {"it-puglia": 100, "it-basilicata": 50}
    assert repo.finished[0]["metrics"]["scopes"] == 2
    assert repo.finished[0]["metrics"]["total"] == 150


@pytest.mark.asyncio
async def test_a_wrapped_job_that_raises_propagates(repo: _Recorder) -> None:
    async def job(_deps: object) -> None:
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError, match="nope"):
        await track_job("limen-test")(job)(object())

    assert repo.finished[0]["status"] == "error"


@pytest.mark.asyncio
async def test_a_wrapped_job_keeps_its_name(repo: _Recorder) -> None:
    """Lo scheduler identifica i job anche dal nome della callable: perderlo
    renderebbe illeggibili i suoi log."""

    async def run_something(_deps: object) -> int:
        return 1

    wrapped = track_job("limen-test")(run_something)

    assert wrapped.__name__ == "run_something"
