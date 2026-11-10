"""``limen qualita-dati`` — il riepilogo notturno sulla qualità dei dati, a mano (#421).

Lo stesso lavoro del passo ``qualita_dati`` della pipeline notturna: job
fermi rispetto alla loro cadenza, job falliti nelle ultime 24 ore, pericoli
con metà delle celle non misurate. Scrive ``qualita_dati_<data>.md`` in
``LIMEN_REPORTS_DIR`` e non tocca il database.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from limen.core.logging import get_logger
from limen.core.qualita_dati import righe, testo
from limen.data.db import lifespan_pool
from limen.data.repos import qualita_dati_repo

log = get_logger(__name__)


async def riepilogo(adesso: datetime | None = None) -> dict[str, Any]:
    """Raccoglie, scrive il report, e ritorna le metriche per ``job_runs``."""
    quando = adesso or datetime.now(UTC)
    fatti = await qualita_dati_repo.raccogli(quando)
    prima = await qualita_dati_repo.settimana_prima(quando)
    cartella = Path(os.getenv("LIMEN_REPORTS_DIR", "reports"))
    cartella.mkdir(parents=True, exist_ok=True)
    out = cartella / f"qualita_dati_{quando:%Y-%m-%d}.md"
    out.write_text(testo(fatti, prima) + "\n", encoding="utf-8")
    problemi = righe(fatti, prima)
    log.info("qualita_dati.done", problemi=len(problemi), report=str(out))
    return {**fatti.metriche(), "problemi": len(problemi), "report": str(out)}


async def run() -> int:
    async with lifespan_pool():
        await riepilogo()
    return 0


__all__ = ["riepilogo", "run"]
