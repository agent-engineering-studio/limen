"""Registranti e richieste dei sensori dei cittadini (#253, migrazione 077).

La mail del registrante si legge solo qui e solo per la CLI dell'operatore e
per la mail di approvazione: nessuna API la espone.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import asyncpg
from shapely.geometry import Point

from limen.data.db import acquire

StatoRichiesta = Literal["in_attesa", "approvata", "respinta"]


@dataclass(frozen=True, slots=True)
class Richiesta:
    id: int
    registrante_id: int
    email: str
    device_id: str
    device_type: str
    lon: float
    lat: float
    cell_id: str | None
    csr: str
    licenza: str
    stato: StatoRichiesta
    certificato: str | None
    creata_at: datetime


_SELECT = """
    SELECT r.id, r.registrante_id, g.email, r.device_id, r.device_type,
           r.lon, r.lat, r.cell_id,
           r.csr, r.licenza, r.stato, r.certificato, r.creata_at
      FROM sensori_richieste r
      JOIN sensori_registranti g ON g.id = r.registrante_id
"""


def _richiesta(row: asyncpg.Record) -> Richiesta:
    return Richiesta(**dict(row))


@asynccontextmanager
async def transazione() -> AsyncIterator[asyncpg.Connection]:
    async with acquire() as conn, conn.transaction():
        yield conn


async def cella_per_punto(lon: float, lat: float) -> str | None:
    async with acquire() as conn:
        cell_id: str | None = await conn.fetchval(
            """
            SELECT id FROM grid_cells
             WHERE ST_Covers(geom, ST_SetSRID(ST_MakePoint($1, $2), 4326))
             ORDER BY id LIMIT 1
            """,
            lon,
            lat,
        )
    return cell_id


async def id_in_uso(device_id: str) -> bool:
    async with acquire() as conn:
        in_uso: bool = await conn.fetchval(
            """
            SELECT EXISTS (SELECT 1 FROM sensor_devices WHERE id = $1)
                OR EXISTS (SELECT 1 FROM sensori_richieste
                            WHERE device_id = $1 AND stato = 'in_attesa')
            """,
            device_id,
        )
    return in_uso


async def registrante_bloccato(conn: asyncpg.Connection, email: str) -> int:
    """Crea il registrante se manca e ne blocca la riga fino alla fine della
    transazione: due invii in parallelo della stessa mail non passano
    entrambi l'ultimo posto della quota. Restituisce l'id."""
    registrante_id: int = await conn.fetchval(
        """
        INSERT INTO sensori_registranti (email) VALUES ($1)
        ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email
        RETURNING id
        """,
        email,
    )
    return registrante_id


async def posti_occupati(conn: asyncpg.Connection, registrante_id: int) -> int:
    """Dispositivi del registrante, revocati compresi, più le richieste in attesa."""
    n: int = await conn.fetchval(
        """
        SELECT (SELECT count(*) FROM sensor_devices WHERE registrante_id = $1)
             + (SELECT count(*) FROM sensori_richieste
                 WHERE registrante_id = $1 AND stato = 'in_attesa')
        """,
        registrante_id,
    )
    return n


async def inserisci_richiesta(
    conn: asyncpg.Connection,
    *,
    registrante_id: int,
    device_id: str,
    device_type: str,
    lon: float,
    lat: float,
    cell_id: str,
    csr: str,
    licenza: str,
) -> int | None:
    """``None`` se lo stesso id ha già una richiesta in attesa (doppio invio)."""
    richiesta_id: int | None = await conn.fetchval(
        """
        INSERT INTO sensori_richieste (
            registrante_id, device_id, device_type, lon, lat, cell_id, csr, licenza
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (device_id) WHERE stato = 'in_attesa' DO NOTHING
        RETURNING id
        """,
        registrante_id,
        device_id,
        device_type,
        lon,
        lat,
        cell_id,
        csr,
        licenza,
    )
    return richiesta_id


async def richiesta(richiesta_id: int) -> Richiesta | None:
    async with acquire() as conn:
        row = await conn.fetchrow(_SELECT + " WHERE r.id = $1", richiesta_id)
    return None if row is None else _richiesta(row)


async def in_attesa() -> list[Richiesta]:
    async with acquire() as conn:
        rows = await conn.fetch(_SELECT + " WHERE r.stato = 'in_attesa' ORDER BY r.id")
    return [_richiesta(r) for r in rows]


class _GiaDecisaError(Exception):
    pass


async def approva(r: Richiesta, *, cell_id: str, certificato: str) -> bool:
    """Il dispositivo nasce al livello 0, offline finché non si collega.

    Niente ``ON CONFLICT``: un id già usato da un altro dispositivo deve far
    fallire l'approvazione, non regalare al registrante quel dispositivo.
    """
    try:
        await _approva(r, cell_id=cell_id, certificato=certificato)
    except _GiaDecisaError:
        return False
    return True


async def _approva(r: Richiesta, *, cell_id: str, certificato: str) -> None:
    async with acquire() as conn, conn.transaction():
        await conn.execute(
            """
            INSERT INTO sensor_devices (
                id, device_type, cell_id, location, status, livello,
                registrante_id, metadata
            ) VALUES ($1, $2, $3, ST_SetSRID($4::geometry, 4326), 'offline', 0, $5, $6::jsonb)
            """,
            r.device_id,
            r.device_type,
            cell_id,
            Point(r.lon, r.lat),
            r.registrante_id,
            json.dumps({"licenza": r.licenza, "richiesta": r.id}),
        )
        esito: str = await conn.execute(
            """
            UPDATE sensori_richieste
               SET stato = 'approvata', certificato = $2, cell_id = $3, decisa_at = now()
             WHERE id = $1 AND stato = 'in_attesa'
            """,
            r.id,
            certificato,
            cell_id,
        )
        if not esito.endswith(" 1"):
            # Un altro operatore l'ha decisa nel frattempo: niente dispositivo.
            raise _GiaDecisaError


async def salva_certificato(richiesta_id: int, certificato: str) -> None:
    """Il certificato appena firmato, prima di tutto il resto: se dopo qualcosa
    fallisce, il rilancio lo riusa invece di firmarne un secondo."""
    async with acquire() as conn:
        await conn.execute(
            """
            UPDATE sensori_richieste SET certificato = $2
             WHERE id = $1 AND stato = 'in_attesa' AND certificato IS NULL
            """,
            richiesta_id,
            certificato,
        )


async def respingi(richiesta_id: int) -> bool:
    async with acquire() as conn:
        esito: str = await conn.execute(
            """
            UPDATE sensori_richieste SET stato = 'respinta', decisa_at = now()
             WHERE id = $1 AND stato = 'in_attesa'
            """,
            richiesta_id,
        )
    return esito.endswith(" 1")


async def registrante_id(email: str) -> int | None:
    async with acquire() as conn:
        rid: int | None = await conn.fetchval(
            "SELECT id FROM sensori_registranti WHERE email = $1", email
        )
    return rid


async def dispositivi_del_registrante(registrante_id: int) -> list[str]:
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT id FROM sensor_devices WHERE registrante_id = $1 ORDER BY id",
            registrante_id,
        )
    return [r["id"] for r in rows]


async def cancella_registrante(registrante_id: int) -> None:
    """Le richieste se ne vanno con lui; i dispositivi restano, staccati.

    La posizione esatta di un dispositivo è spesso il giardino di casa: senza
    la mail identifica ancora una persona. Torna al centroide della sua cella.
    """
    async with acquire() as conn, conn.transaction():
        await conn.execute(
            """
            UPDATE sensor_devices d
               SET location = COALESCE(
                       (SELECT g.centroid FROM grid_cells g WHERE g.id = d.cell_id), d.location),
                   metadata = d.metadata - 'richiesta',
                   updated_at = now()
             WHERE d.registrante_id = $1
            """,
            registrante_id,
        )
        await conn.execute("DELETE FROM sensori_registranti WHERE id = $1", registrante_id)


__all__ = [
    "Richiesta",
    "StatoRichiesta",
    "approva",
    "cancella_registrante",
    "cella_per_punto",
    "dispositivi_del_registrante",
    "id_in_uso",
    "in_attesa",
    "inserisci_richiesta",
    "posti_occupati",
    "registrante_bloccato",
    "registrante_id",
    "respingi",
    "richiesta",
    "salva_certificato",
    "transazione",
]
