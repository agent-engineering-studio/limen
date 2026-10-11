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
    ingresso: str | None = None,
) -> None:
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO spiegazioni_regione
                (aoi_id, hazard_type, run_id, livello, scritta, modello, ripiego, testo, analisi,
                 ingresso)
            VALUES ($1, $2, $3, $4, now(), $5, $6, $7, $8::jsonb, $9)
            ON CONFLICT (aoi_id, hazard_type) DO UPDATE SET
                run_id = EXCLUDED.run_id,
                livello = EXCLUDED.livello,
                scritta = EXCLUDED.scritta,
                modello = EXCLUDED.modello,
                ripiego = EXCLUDED.ripiego,
                testo = EXCLUDED.testo,
                analisi = EXCLUDED.analisi,
                ingresso = EXCLUDED.ingresso,
                -- Il verdetto era sul testo di prima.
                fedelta = NULL,
                fedelta_at = NULL
            """,
            aoi_id,
            hazard.value,
            run_id,
            livello,
            modello,
            ripiego,
            testo,
            json.dumps(analisi, default=str) if analisi is not None else None,
            ingresso,
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


@dataclass(frozen=True, slots=True)
class DaGiudicare:
    aoi_id: str
    hazard: HazardType
    scritta: datetime
    modello: str
    testo: str
    ingresso: str


async def da_giudicare(*, hours: int, limite: int) -> list[DaGiudicare]:
    """Un campione **casuale** delle spiegazioni dell'AI non ancora giudicate.

    Casuale e non «le più recenti», per la stessa ragione di `review-alerts`:
    le spiegazioni di una stessa ora raccontano lo stesso fronte meteo, e un
    campione correlato misurerebbe un temporale, non il modello. Solo quelle
    con `ingresso`: senza i dati da cui sono nate non c'è niente contro cui
    confrontarle.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT aoi_id, hazard_type, scritta, modello, testo, ingresso
            FROM spiegazioni_regione
            WHERE NOT ripiego
              AND ingresso IS NOT NULL
              AND fedelta IS NULL
              AND scritta > now() - make_interval(hours => $1)
            ORDER BY random()
            LIMIT $2
            """,
            hours,
            limite,
        )
    return [
        DaGiudicare(
            aoi_id=str(r["aoi_id"]),
            hazard=HazardType(r["hazard_type"]),
            scritta=r["scritta"],
            modello=str(r["modello"]),
            testo=str(r["testo"]),
            ingresso=str(r["ingresso"]),
        )
        for r in rows
    ]


async def scrivi_fedelta(
    *, aoi_id: str, hazard: HazardType, scritta: datetime, fedelta: dict[str, Any]
) -> bool:
    """Il verdetto, solo se la spiegazione è ancora quella giudicata.

    Un controllo con un modello lento dura minuti: se nel frattempo
    `briefing_enrichment` ha riscritto il testo, il verdetto parlerebbe di un
    testo che non c'è più. Ritorna ``False`` in quel caso.
    """
    async with acquire() as conn:
        esito = await conn.execute(
            """
            UPDATE spiegazioni_regione
            SET fedelta = $4::jsonb, fedelta_at = now()
            WHERE aoi_id = $1 AND hazard_type = $2 AND scritta = $3
            """,
            aoi_id,
            hazard.value,
            scritta,
            json.dumps(fedelta, default=str),
        )
    return str(esito).endswith(" 1")
