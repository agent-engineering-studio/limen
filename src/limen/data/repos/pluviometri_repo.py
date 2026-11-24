"""Pluviometri regionali e la loro pioggia oraria (migrazione 099).

Una riga per pluviometro e giorno UTC con 24 valori: ``mm[i]`` è la pioggia
dell'ora che finisce a ``giorno + i`` ore, ``None`` se non misurata. Un giorno
senza riga è un giorno non misurato, mai asciutto.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from limen.data.db import acquire


@dataclass(frozen=True, slots=True)
class Stazione:
    id: str
    fonte: str
    codice: str
    nome: str
    lon: float
    lat: float
    quota_m: float | None
    dal: date | None
    al: date | None


@dataclass(frozen=True, slots=True)
class GiornoPioggia:
    pluviometro_id: str
    giorno: date
    mm: tuple[float | None, ...]
    validata: bool | None


@dataclass(frozen=True, slots=True)
class Vicino:
    stazione: Stazione
    distanza_km: float


def id_di(fonte: str, codice: str) -> str:
    return f"{fonte}:{codice}"


def per_giorno(
    ore: dict[datetime, list[float | None]],
    ids: Sequence[str],
    validata: dict[tuple[str, date], bool | None] | None = None,
) -> list[GiornoPioggia]:
    """Dalle ore UTC ``(h-1, h]`` → mm per pluviometro alle righe giornaliere.

    Un giorno senza nemmeno un'ora misurata non diventa una riga.
    """
    giorni: dict[tuple[str, date], list[float | None]] = {}
    for ora, valori in ore.items():
        inizio = ora.astimezone(UTC) - timedelta(hours=1)
        for pid, mm in zip(ids, valori, strict=True):
            riga = giorni.setdefault((pid, inizio.date()), [None] * 24)
            riga[inizio.hour] = mm
    return [
        GiornoPioggia(
            pluviometro_id=pid,
            giorno=g,
            mm=tuple(mm),
            validata=(validata or {}).get((pid, g)),
        )
        for (pid, g), mm in sorted(giorni.items())
        if any(v is not None for v in mm)
    ]


async def salva_stazioni(stazioni: Sequence[Stazione]) -> int:
    async with acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO pluviometri (id, fonte, codice, nome, quota_m, geom, dal, al)
            VALUES ($1, $2, $3, $4, $5, ST_SetSRID(ST_MakePoint($6, $7), 4326), $8, $9)
            ON CONFLICT (id) DO UPDATE SET
                nome = EXCLUDED.nome, quota_m = EXCLUDED.quota_m, geom = EXCLUDED.geom,
                dal = EXCLUDED.dal, al = EXCLUDED.al, aggiornato_at = now()
            WHERE (pluviometri.nome, pluviometri.quota_m, pluviometri.dal, pluviometri.al)
                  IS DISTINCT FROM (EXCLUDED.nome, EXCLUDED.quota_m, EXCLUDED.dal, EXCLUDED.al)
               OR NOT ST_Equals(pluviometri.geom, EXCLUDED.geom)
            """,
            [
                (s.id, s.fonte, s.codice, s.nome, s.quota_m, s.lon, s.lat, s.dal, s.al)
                for s in stazioni
            ],
        )
    return len(stazioni)


async def sostituisci(fonte: str, dal: date, al: date, giorni: Sequence[GiornoPioggia]) -> int:
    """Riscrive i giorni ``[dal, al]`` della ``fonte``: un'ora che la fonte non
    dà più per misurata deve sparire, non restare col valore vecchio."""
    async with acquire() as conn, conn.transaction():
        await conn.execute(
            """
            DELETE FROM pioggia_pluviometri p USING pluviometri s
             WHERE s.id = p.pluviometro_id AND s.fonte = $1 AND p.giorno BETWEEN $2 AND $3
            """,
            fonte,
            dal,
            al,
        )
        await conn.executemany(
            "INSERT INTO pioggia_pluviometri (pluviometro_id, giorno, mm, validata) "
            "VALUES ($1, $2, $3, $4)",
            [
                (g.pluviometro_id, g.giorno, list(g.mm), g.validata)
                for g in giorni
                if dal <= g.giorno <= al
            ],
        )
    return sum(dal <= g.giorno <= al for g in giorni)


async def vicini(
    lon: float,
    lat: float,
    *,
    raggio_km: float,
    dal: date,
    al: date,
    limite: int = 3,
) -> list[Vicino]:
    """I pluviometri entro ``raggio_km`` da un punto e attivi fra ``dal`` e ``al``,
    dal più vicino: una stazione dismessa prima della finestra non la misura."""
    async with acquire() as conn:
        righe = await conn.fetch(
            """
            SELECT id, fonte, codice, nome, quota_m, ST_X(geom) AS lon, ST_Y(geom) AS lat,
                   dal, al,
                   ST_Distance(geom::geography, ST_MakePoint($1, $2)::geography) / 1000 AS km
              FROM pluviometri
             WHERE ST_DWithin(geom::geography, ST_MakePoint($1, $2)::geography, $3 * 1000)
               AND (dal IS NULL OR dal <= $6) AND (al IS NULL OR al >= $5)
             ORDER BY km
             LIMIT $4
            """,
            lon,
            lat,
            raggio_km,
            limite,
            dal,
            al,
        )
    return [
        Vicino(
            stazione=Stazione(
                id=r["id"],
                fonte=r["fonte"],
                codice=r["codice"],
                nome=r["nome"],
                lon=float(r["lon"]),
                lat=float(r["lat"]),
                quota_m=r["quota_m"],
                dal=r["dal"],
                al=r["al"],
            ),
            distanza_km=round(float(r["km"]), 2),
        )
        for r in righe
    ]


async def serie(
    pluviometro_id: str, start: datetime, end: datetime
) -> tuple[dict[datetime, float | None], bool | None]:
    """Ore ``(h-1, h]`` in ``(start, end]`` → mm (``None`` = non misurata), e se
    i giorni letti sono tutti validati (``None`` se la fonte non lo dice)."""
    primo = (start.astimezone(UTC)).date()
    ultimo = (end.astimezone(UTC) - timedelta(hours=1)).date()
    async with acquire() as conn:
        righe = await conn.fetch(
            "SELECT giorno, mm, validata FROM pioggia_pluviometri "
            "WHERE pluviometro_id = $1 AND giorno BETWEEN $2 AND $3",
            pluviometro_id,
            primo,
            ultimo,
        )
    per_ora: dict[datetime, float | None] = {}
    for r in righe:
        base = datetime.combine(r["giorno"], time(), tzinfo=UTC)
        for i, mm in enumerate(r["mm"], start=1):
            # real: 0.2 torna 0.2000000029.
            per_ora[base + timedelta(hours=i)] = None if mm is None else round(float(mm), 2)
    out: dict[datetime, float | None] = {}
    ora = start.astimezone(UTC).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    while ora <= end:
        out[ora] = per_ora.get(ora)
        ora += timedelta(hours=1)
    validate = [r["validata"] for r in righe]
    if not validate or any(v is None for v in validate):
        return out, None
    return out, all(validate)
