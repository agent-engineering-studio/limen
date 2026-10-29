"""I candidati della raccolta dalla stampa (migrazione 084, #347)."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Any

from limen.core.models.hazard import HazardType
from limen.data.db import acquire


@dataclass(frozen=True, slots=True)
class Candidato:
    hazard: HazardType
    giorno: date
    parte: str
    luogo: str
    regione: str | None
    nomi_comuni: tuple[str, ...]
    fonti: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class Salvato:
    id: int
    fonti: tuple[dict[str, Any], ...]
    testate: int
    slug: str | None


def aoi_della_regione(regione: str | None) -> str | None:
    """``Valle d'Aosta`` → ``it-valle-d-aosta``: l'id delle AOI regionali."""
    if not regione:
        return None
    ascii_ = unicodedata.normalize("NFKD", regione).encode("ascii", "ignore").decode()
    return "it-" + re.sub(r"[^a-z]+", "-", ascii_.lower()).strip("-")


def conta_testate(fonti: tuple[dict[str, Any], ...]) -> int:
    """Le testate diverse: due titoli dello stesso giornale sono una fonte."""
    return len({f["testata"].strip().casefold() for f in fonti if f.get("testata")})


async def risolvi_comuni(nomi: tuple[str, ...], regione: str | None) -> list[str]:
    """I codici ISTAT dei comuni nominati, o ``[]`` se uno non si risolve.

    Gli omonimi esistono (Castro, Peglio, Samone): con più comuni dello
    stesso nome vince quello della regione dell'evento, e senza regione il
    nome resta irrisolto. Meglio un candidato in sospeso che una verità nel
    comune sbagliato.
    """
    aoi = aoi_della_regione(regione)
    codici: list[str] = []
    async with acquire() as conn:
        for nome in nomi:
            righe = await conn.fetch(
                "SELECT istat_code, aoi_id FROM comuni WHERE lower(name) = lower($1)", nome.strip()
            )
            scelti = [r["istat_code"] for r in righe if len(righe) == 1 or r["aoi_id"] == aoi]
            if len(scelti) != 1:
                return []
            codici.append(scelti[0])
    return codici


async def fondi(c: Candidato) -> Salvato:
    """Inserisce il candidato o lo unisce a quello già visto: stesso pericolo,
    un comune in comune, giorno entro ±1. Le fonti si uniscono per URL."""
    nomi = [n.casefold() for n in c.nomi_comuni]
    async with acquire() as conn, conn.transaction():
        riga = await conn.fetchrow(
            """
            SELECT id, fonti FROM candidati_eventi
            WHERE hazard_type = $1::hazard_type
              AND giorno BETWEEN $2::date - 1 AND $2::date + 1
              AND (SELECT array_agg(lower(n)) FROM unnest(nomi_comuni) n) && $3::text[]
              -- Castro in Lombardia e Castro in Puglia non sono lo stesso evento.
              AND (regione IS NULL OR $4::text IS NULL OR lower(regione) = lower($4::text))
            ORDER BY visto_ultimo DESC
            LIMIT 1
            FOR UPDATE
            """,
            c.hazard.value,
            c.giorno,
            nomi,
            c.regione,
        )
        fonti = list(c.fonti)
        if riga is not None:
            viste = {f["url"] for f in fonti}
            fonti = [f for f in json.loads(riga["fonti"]) if f["url"] not in viste] + fonti
        testate = conta_testate(tuple(fonti))
        if riga is None:
            salvato = await conn.fetchrow(
                """
                INSERT INTO candidati_eventi
                    (hazard_type, giorno, parte, luogo, regione, nomi_comuni, fonti, testate, stato)
                VALUES ($1::hazard_type, $2, $3, $4, $5, $6, $7::jsonb, $8, 'una_testata')
                RETURNING id, slug
                """,
                c.hazard.value,
                c.giorno,
                c.parte,
                c.luogo,
                c.regione,
                list(c.nomi_comuni),
                json.dumps(fonti),
                testate,
            )
        else:
            salvato = await conn.fetchrow(
                """
                UPDATE candidati_eventi
                SET fonti = $2::jsonb, testate = $3, visto_ultimo = now()
                WHERE id = $1
                RETURNING id, slug
                """,
                riga["id"],
                json.dumps(fonti),
                testate,
            )
    assert salvato is not None
    return Salvato(id=salvato["id"], fonti=tuple(fonti), testate=testate, slug=salvato["slug"])


async def segna(id_: int, *, stato: str, comuni: list[str], slug: str | None) -> None:
    async with acquire() as conn:
        await conn.execute(
            "UPDATE candidati_eventi SET stato = $2, comuni = $3, slug = $4 WHERE id = $1",
            id_,
            stato,
            comuni,
            slug,
        )
