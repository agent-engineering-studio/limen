"""Quanto prima Limen ha visto un evento: ``anticipo.sql`` sul database.

La stessa misura per il fact check a mano (``limen anticipo``, la skill) e per
la raccolta quotidiana (#347): una query sola, così i due non possono dare
esiti diversi per lo stesso evento.
"""

from __future__ import annotations

import json
from datetime import datetime
from functools import cache
from importlib import resources
from typing import Any

from limen.core.models.hazard import HazardType
from limen.data.db import acquire


@cache
def _sql() -> str:
    return resources.files(__package__).joinpath("anticipo.sql").read_text(encoding="utf-8")


async def misura(
    *, comuni: list[str], hazard: HazardType, evento_at: datetime, tolleranza_ore: int
) -> dict[str, Any]:
    async with acquire() as conn:
        grezzo = await conn.fetchval(_sql(), comuni, hazard.value, evento_at, tolleranza_ore)
    risultato: dict[str, Any] = json.loads(grezzo)
    return risultato
