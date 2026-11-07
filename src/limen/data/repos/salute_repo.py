"""La pagina «Salute» (#408): fonti esterne, celle non misurate, database.

``riversa`` scrive (e solleva: la chiama il battito del worker, che lo
tollera); le letture degradano a un risultato neutro come ogni lettura.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from limen.core.logging import get_logger
from limen.data.db import acquire
from limen.integrations.salute import Esito

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RigaFonte:
    fonte: str
    ultimo_ok: datetime | None
    ultimo_errore: datetime | None
    errore: str | None


@dataclass(frozen=True, slots=True)
class Misurate:
    non_misurate: int
    totali: int


async def riversa(esiti: Mapping[str, Esito]) -> None:
    """Fonde il registro del processo in ``salute_fonti``: vince il più recente."""
    if not esiti:
        return
    async with acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO salute_fonti (fonte, ultimo_ok, ultimo_errore, errore, aggiornato_il)
            VALUES ($1, $2, $3, $4, now())
            ON CONFLICT (fonte) DO UPDATE SET
                ultimo_ok = GREATEST(salute_fonti.ultimo_ok, EXCLUDED.ultimo_ok),
                ultimo_errore = GREATEST(salute_fonti.ultimo_errore, EXCLUDED.ultimo_errore),
                errore = CASE
                    WHEN EXCLUDED.ultimo_errore IS NOT NULL AND (
                        salute_fonti.ultimo_errore IS NULL
                        OR EXCLUDED.ultimo_errore >= salute_fonti.ultimo_errore)
                    THEN EXCLUDED.errore
                    ELSE salute_fonti.errore END,
                aggiornato_il = now()
            """,
            [(f, e.ultimo_ok, e.ultimo_errore, e.errore) for f, e in esiti.items()],
        )


async def fonti() -> list[RigaFonte]:
    try:
        async with acquire() as conn:
            rows = await conn.fetch(
                "SELECT fonte, ultimo_ok, ultimo_errore, errore FROM salute_fonti"
            )
    except Exception as exc:
        log.warning("integration.degraded", label="salute.fonti", error=str(exc))
        return []
    return [RigaFonte(r["fonte"], r["ultimo_ok"], r["ultimo_errore"], r["errore"]) for r in rows]


async def misurate() -> dict[str, Misurate]:
    """Per pericolo, le celle dell'ultima valutazione senza il dato dinamico."""
    try:
        async with acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT hazard_type::text AS pericolo,
                       count(*) FILTER (WHERE measured IS FALSE) AS non_misurate,
                       count(*) AS totali
                FROM latest_risk
                GROUP BY hazard_type
                """
            )
    except Exception as exc:
        log.warning("integration.degraded", label="salute.misurate", error=str(exc))
        return {}
    return {r["pericolo"]: Misurate(int(r["non_misurate"]), int(r["totali"])) for r in rows}


async def dimensione_db_gb() -> float | None:
    try:
        async with acquire() as conn:
            byte = await conn.fetchval("SELECT pg_database_size(current_database())")
    except Exception as exc:
        log.warning("integration.degraded", label="salute.db_size", error=str(exc))
        return None
    return round(int(byte) / 1e9, 1)
