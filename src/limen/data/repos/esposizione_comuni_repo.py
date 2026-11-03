"""``esposizione_comuni`` (migrazione 085): gli indicatori ISPRA per comune."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from limen.data.db import acquire

if TYPE_CHECKING:
    from limen.integrations.idrogeo.esposizione import EsposizioneComune

#: Le colonne che l'API dei comuni espone; `indicatori` resta nel database.
CAMPI_PUBBLICI = (
    "pop_residenti",
    "pop_frana_p3p4",
    "pop_frana_p3p4_pct",
    "pop_idraulica_p2",
    "pop_idraulica_p2_pct",
    "edifici",
    "imprese",
)


async def sostituisci(righe: Sequence[EsposizioneComune], *, version_id: int) -> int:
    """Scrive la fotografia nuova al posto della vecchia, in una transazione.

    Al posto e non sopra: un comune che ISPRA non elenca più (una fusione)
    non deve restare con i numeri di prima.
    """
    async with acquire() as conn, conn.transaction():
        await conn.execute("DELETE FROM esposizione_comuni")
        await conn.executemany(
            """
            INSERT INTO esposizione_comuni (
                istat_code, nome, pop_residenti, pop_frana_p3p4, pop_frana_p3p4_pct,
                pop_idraulica_p2, pop_idraulica_p2_pct, edifici, imprese,
                indicatori, dataset_version_id, aggiornato
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11, now())
            """,
            [
                (
                    r.istat_code,
                    r.nome,
                    r.pop_residenti,
                    r.pop_frana_p3p4,
                    r.pop_frana_p3p4_pct,
                    r.pop_idraulica_p2,
                    r.pop_idraulica_p2_pct,
                    r.edifici,
                    r.imprese,
                    json.dumps(r.indicatori),
                    version_id,
                )
                for r in righe
            ],
        )
    return len(righe)


async def per_comuni(conn: Any, istat_codes: Sequence[str]) -> dict[str, dict[str, Any]]:
    """I campi pubblici dei comuni chiesti; un comune senza riga non c'è."""
    if not istat_codes:
        return {}
    rows = await conn.fetch(
        f"SELECT istat_code, {', '.join(CAMPI_PUBBLICI)}, aggiornato "
        "FROM esposizione_comuni WHERE istat_code = ANY($1::text[])",
        list(istat_codes),
    )
    return {
        str(r["istat_code"]): {
            **{c: r[c] for c in CAMPI_PUBBLICI},
            "aggiornato": r["aggiornato"].isoformat(),
        }
        for r in rows
    }


__all__ = ["CAMPI_PUBBLICI", "per_comuni", "sostituisci"]
