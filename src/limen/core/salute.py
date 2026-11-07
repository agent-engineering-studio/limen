"""Le regole della pagina «Salute» (#408): quando una fonte è in errore, quale
pericolo ne risente, come si legge un passo del notturno.

Pure: niente database. La route le traduce, i repo portano i dati.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Literal

from limen.core.models.hazard import HazardType
from limen.data.repos.job_runs_repo import JobRun
from limen.integrations.salute import FONTI

StatoPasso = Literal["ok", "avviso", "errore", "saltato", "in_corso"]


def in_errore(ultimo_ok: datetime | None, ultimo_errore: datetime | None) -> bool:
    """L'ultimo esito è un errore: un 429 persistente non ha un successo dopo."""
    return ultimo_errore is not None and (ultimo_ok is None or ultimo_errore > ultimo_ok)


def cause(pericolo: HazardType, fonti_in_errore: Iterable[str]) -> list[str]:
    """Le fonti in errore da cui dipende il pericolo, per nome."""
    return [
        FONTI[f].nome
        for f in sorted(fonti_in_errore)
        if f in FONTI and pericolo in FONTI[f].pericoli
    ]


def passo(run: JobRun) -> tuple[StatoPasso, str | None]:
    """Lo stato di un passo di ``job_runs`` e una nota leggibile, senza segreti."""
    m = run.metrics
    if run.finished_at is None:
        return "in_corso", None
    if run.status == "skipped":
        return "saltato", _testo(m.get("reason"))
    if run.status == "error" or m.get("status") == "error":
        return "errore", _testo(run.error or m.get("error_type"))
    if m.get("avviso"):
        avvisi = m.get("avvisi")
        nota = "; ".join(map(str, avvisi)) if isinstance(avvisi, list) else None
        return "avviso", nota
    return "ok", None


def _testo(x: object) -> str | None:
    return str(x) if x else None
