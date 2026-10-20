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
    #: La CSR, oppure DevEUI e applicazione TTN per un sensore LoRaWAN (#266).
    csr: str | None
    dev_eui: str | None
    ttn_applicazione: str | None
    licenza: str
    stato: StatoRichiesta
    certificato: str | None
    creata_at: datetime


_SELECT = """
    SELECT r.id, r.registrante_id, g.email, r.device_id, r.device_type,
           r.lon, r.lat, r.cell_id,
           r.csr, r.dev_eui, r.ttn_applicazione, r.licenza, r.stato, r.certificato, r.creata_at
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


async def dev_eui_in_uso(dev_eui: str) -> bool:
    async with acquire() as conn:
        in_uso: bool = await conn.fetchval(
            """
            SELECT EXISTS (SELECT 1 FROM sensor_devices WHERE dev_eui = $1)
                OR EXISTS (SELECT 1 FROM sensori_richieste
                            WHERE dev_eui = $1 AND stato = 'in_attesa')
            """,
            dev_eui,
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
    csr: str | None,
    licenza: str,
    dev_eui: str | None = None,
    ttn_applicazione: str | None = None,
) -> int | None:
    """``None`` se lo stesso id o DevEUI ha già una richiesta in attesa (doppio
    invio)."""
    richiesta_id: int | None = await conn.fetchval(
        """
        INSERT INTO sensori_richieste (
            registrante_id, device_id, device_type, lon, lat, cell_id, csr, licenza,
            dev_eui, ttn_applicazione
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        ON CONFLICT DO NOTHING
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
        dev_eui,
        ttn_applicazione,
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


class ApplicazioneAltruiError(Exception):
    """L'applicazione TTN è già registrata da un altro registrante."""


async def approva(r: Richiesta, *, cell_id: str, certificato: str, chiave: bytes) -> bool:
    """Il dispositivo nasce al livello 0, offline finché non si collega.

    Niente ``ON CONFLICT``: un id già usato da un altro dispositivo deve far
    fallire l'approvazione, non regalare al registrante quel dispositivo.
    """
    try:
        await _approva(r, cell_id=cell_id, certificato=certificato, chiave=chiave)
    except _GiaDecisaError:
        return False
    return True


async def _approva(r: Richiesta, *, cell_id: str, certificato: str, chiave: bytes) -> None:
    async with acquire() as conn, conn.transaction():
        await _crea_dispositivo(conn, r, cell_id=cell_id, certificato=certificato, chiave=chiave)


async def _crea_dispositivo(
    conn: asyncpg.Connection,
    r: Richiesta,
    *,
    cell_id: str,
    certificato: str | None,
    chiave: bytes | None,
) -> None:
    await conn.execute(
        """
        INSERT INTO sensor_devices (
            id, device_type, cell_id, location, status, livello,
            registrante_id, metadata, chiave_pubblica, dev_eui, ttn_applicazione
        ) VALUES ($1, $2, $3, ST_SetSRID($4::geometry, 4326), 'offline', 0, $5, $6::jsonb, $7,
                  $8, $9)
        """,
        r.device_id,
        r.device_type,
        cell_id,
        Point(r.lon, r.lat),
        r.registrante_id,
        json.dumps({"licenza": r.licenza, "richiesta": r.id}),
        chiave,
        r.dev_eui,
        r.ttn_applicazione,
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


async def approva_lorawan(r: Richiesta, *, cell_id: str, segreto_sha256: bytes) -> bool | None:
    """Crea il dispositivo LoRaWAN e, se manca, l'applicazione TTN con lo
    SHA-256 del segreto nuovo. ``True`` se l'applicazione è nuova (il segreto
    va mandato), ``False`` se c'era già (vale quello già mandato), ``None`` se
    la richiesta era già decisa. Solleva :class:`ApplicazioneAltruiError` se
    l'applicazione è di un altro registrante."""
    assert r.ttn_applicazione is not None and r.dev_eui is not None
    try:
        async with acquire() as conn, conn.transaction():
            nuova = await conn.fetchval(
                """
                INSERT INTO sensori_ttn (applicazione, registrante_id, segreto_sha256)
                VALUES ($1, $2, $3) ON CONFLICT (applicazione) DO NOTHING
                RETURNING true
                """,
                r.ttn_applicazione,
                r.registrante_id,
                segreto_sha256,
            )
            if not nuova:
                proprietario = await conn.fetchval(
                    "SELECT registrante_id FROM sensori_ttn WHERE applicazione = $1 FOR SHARE",
                    r.ttn_applicazione,
                )
                if proprietario != r.registrante_id:
                    raise ApplicazioneAltruiError(r.ttn_applicazione)
            await _crea_dispositivo(conn, r, cell_id=cell_id, certificato=None, chiave=None)
    except _GiaDecisaError:
        return None
    return bool(nuova)


async def ruota_segreto_ttn(applicazione: str, segreto_sha256: bytes) -> str | None:
    """Sostituisce il segreto del webhook; restituisce la mail del registrante,
    ``None`` se l'applicazione non c'è."""
    async with acquire() as conn:
        email: str | None = await conn.fetchval(
            """
            UPDATE sensori_ttn t SET segreto_sha256 = $2
              FROM sensori_registranti g
             WHERE t.applicazione = $1 AND g.id = t.registrante_id
            RETURNING g.email
            """,
            applicazione,
            segreto_sha256,
        )
    return email


async def chiave_se_manca(device_id: str, chiave: bytes) -> bool:
    """La chiave di un dispositivo approvato prima della 081 (#265). Una chiave
    già scritta non si sostituisce: viene dalla stessa CSR."""
    async with acquire() as conn:
        esito: str = await conn.execute(
            "UPDATE sensor_devices SET chiave_pubblica = $2, updated_at = now() "
            "WHERE id = $1 AND chiave_pubblica IS NULL",
            device_id,
            chiave,
        )
    return esito.endswith(" 1")


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
                   -- Il DevEUI è del dispositivo fisico: liberato, chi lo
                   -- riceve dopo può registrarlo (#266). L'applicazione si
                   -- stacca qui e non con il SET NULL della 082: nella stessa
                   -- DELETE la cascata su registrante_id ricontrollerebbe la
                   -- chiave di una riga di sensori_ttn già cancellata.
                   dev_eui = NULL,
                   ttn_applicazione = NULL,
                   updated_at = now()
             WHERE d.registrante_id = $1
            """,
            registrante_id,
        )
        await conn.execute("DELETE FROM sensori_registranti WHERE id = $1", registrante_id)


__all__ = [
    "ApplicazioneAltruiError",
    "Richiesta",
    "StatoRichiesta",
    "approva",
    "approva_lorawan",
    "cancella_registrante",
    "cella_per_punto",
    "chiave_se_manca",
    "dev_eui_in_uso",
    "dispositivi_del_registrante",
    "id_in_uso",
    "in_attesa",
    "inserisci_richiesta",
    "posti_occupati",
    "registrante_bloccato",
    "registrante_id",
    "respingi",
    "richiesta",
    "ruota_segreto_ttn",
    "salva_certificato",
    "transazione",
]
