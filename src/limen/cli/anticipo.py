"""``limen anticipo ISTAT PERICOLO QUANDO [--tolleranza ORE]`` — quanto prima
Limen ha visto un evento, come JSON su stdout.

È la misura del fact check a mano (skill ``limen-fact-check``, §4): la stessa
query della raccolta quotidiana (``anticipo_repo``), così i due non possono
dare esiti diversi. Non scrive niente.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime

from limen.core.models.hazard import HazardType
from limen.data.db import lifespan_pool
from limen.data.repos import anticipo_repo


async def run(istat: str, pericolo: str, quando: str, tolleranza: int) -> int:
    evento_at = datetime.fromisoformat(quando)
    if evento_at.tzinfo is None:
        raise SystemExit("l'ora dell'evento vuole il fuso: 2026-10-10T15:00+02:00")
    async with lifespan_pool():
        misura = await anticipo_repo.misura(
            comuni=[c.strip() for c in istat.split(",") if c.strip()],
            hazard=HazardType(pericolo),
            evento_at=evento_at,
            tolleranza_ore=tolleranza,
        )
    sys.stdout.write(json.dumps(misura, ensure_ascii=False) + "\n")
    return 0
