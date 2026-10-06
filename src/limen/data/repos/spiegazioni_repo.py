"""Le spiegazioni dell'AI per (regione, pericolo) — migrazione 064."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from limen.core.models.hazard import HazardType
from limen.data.db import acquire


@dataclass(frozen=True, slots=True)
class Spiegazione:
    aoi_id: str
    hazard: HazardType
    run_id: int
    livello: str
    scritta: datetime
    modello: str
    ripiego: bool
    testo: str
    analisi: dict[str, Any] | None


async def scrivi(
    *,
    aoi_id: str,
    hazard: HazardType,
    run_id: int,
    livello: str,
    modello: str,
    ripiego: bool,
    testo: str,
    analisi: dict[str, Any] | None,
) -> None:
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO spiegazioni_regione
                (aoi_id, hazard_type, run_id, livello, scritta, modello, ripiego, testo, analisi)
            VALUES ($1, $2, $3, $4, now(), $5, $6, $7, $8::jsonb)
            ON CONFLICT (aoi_id, hazard_type) DO UPDATE SET
                run_id = EXCLUDED.run_id,
                livello = EXCLUDED.livello,
                scritta = EXCLUDED.scritta,
                modello = EXCLUDED.modello,
                ripiego = EXCLUDED.ripiego,
                testo = EXCLUDED.testo,
                analisi = EXCLUDED.analisi
            """,
            aoi_id,
            hazard.value,
            run_id,
            livello,
            modello,
            ripiego,
            testo,
            json.dumps(analisi, default=str) if analisi is not None else None,
        )


async def leggi(aoi_id: str, hazard: HazardType) -> Spiegazione | None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT aoi_id, hazard_type, run_id, livello, scritta, modello, ripiego, testo, analisi
            FROM spiegazioni_regione
            WHERE aoi_id = $1 AND hazard_type = $2
            """,
            aoi_id,
            hazard.value,
        )
    if row is None:
        return None
    analisi = row["analisi"]
    if isinstance(analisi, str):
        analisi = json.loads(analisi)
    return Spiegazione(
        aoi_id=str(row["aoi_id"]),
        hazard=HazardType(row["hazard_type"]),
        run_id=int(row["run_id"]),
        livello=str(row["livello"]),
        scritta=row["scritta"],
        modello=str(row["modello"]),
        ripiego=bool(row["ripiego"]),
        testo=str(row["testo"]),
        analisi=analisi,
    )


async def recenti(hours: int) -> dict[tuple[str, str], str]:
    """``(regione, pericolo) → classe`` delle spiegazioni scritte dall'AI
    nelle ultime ``hours`` ore. Un ripiego non conta: va riprovato."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT aoi_id, hazard_type, livello
            FROM spiegazioni_regione
            WHERE NOT ripiego AND scritta > now() - make_interval(hours => $1)
            """,
            hours,
        )
    return {(str(r["aoi_id"]), str(r["hazard_type"])): str(r["livello"]) for r in rows}
