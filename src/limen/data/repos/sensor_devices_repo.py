"""Sensor-device (SensorThings ``Thing``) registry.

The MQTT ingestor calls :func:`get_device` to resolve a ``thing_id`` to
its cell binding + calibration. The static loader for demo deployments
uses :func:`upsert_many`.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry

from limen.core.logging import get_logger
from limen.data.db import acquire

log = get_logger(__name__)


SensorStatus = Literal["online", "offline", "quarantined"]

# 0 osservatore, 1 verificato, 2 istituzionale (migrazione 075, #251).
SensorLivello = Literal[0, 1, 2]

# L'unico livello che il rollup orario porta allo scoring e alle allerte: una
# misura di un dispositivo di terzi non deve poter abbassare M né forzare
# `hard_escalation`.
LIVELLO_SCORING: SensorLivello = 2


@dataclass(frozen=True, slots=True)
class SensorDevice:
    id: str
    device_type: str
    cell_id: str | None
    location: BaseGeometry
    calibration: dict[str, Any]
    status: SensorStatus = "online"
    last_seen_at: datetime | None = None
    metadata: dict[str, Any] | None = None
    # Fuori dallo scoring finché qualcuno non dice il contrario.
    livello: SensorLivello = 0


async def upsert_many(items: Iterable[SensorDevice]) -> int:
    """Insert-or-update each device by id.

    ``livello`` is written on insert only: a registry re-sync that omits it
    would otherwise promote an observer to institutional through the
    dataclass default.
    """
    items_list = list(items)
    if not items_list:
        return 0
    async with acquire() as conn, conn.transaction():
        for it in items_list:
            calibration_json = json.dumps(it.calibration or {}, default=str)
            metadata_json = json.dumps(it.metadata or {}, default=str)
            await conn.execute(
                """
                INSERT INTO sensor_devices (
                    id, device_type, cell_id, location,
                    calibration, status, last_seen_at, metadata, livello
                ) VALUES (
                    $1, $2, $3, ST_SetSRID($4::geometry, 4326),
                    $5::jsonb, $6, $7, $8::jsonb, $9
                )
                ON CONFLICT (id) DO UPDATE
                SET device_type = EXCLUDED.device_type,
                    cell_id     = EXCLUDED.cell_id,
                    location    = EXCLUDED.location,
                    calibration = EXCLUDED.calibration,
                    status      = EXCLUDED.status,
                    last_seen_at = COALESCE(EXCLUDED.last_seen_at,
                                            sensor_devices.last_seen_at),
                    metadata    = EXCLUDED.metadata,
                    updated_at  = now()
                """,
                it.id,
                it.device_type,
                it.cell_id,
                it.location,
                calibration_json,
                it.status,
                it.last_seen_at,
                metadata_json,
                it.livello,
            )
    log.info("sensor_devices.upsert_many", count=len(items_list))
    return len(items_list)


async def get_device(device_id: str) -> SensorDevice | None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, device_type, cell_id, location,
                   calibration, status, last_seen_at, metadata, livello
            FROM sensor_devices
            WHERE id = $1
            """,
            device_id,
        )
    if row is None:
        return None
    calibration = row["calibration"]
    if isinstance(calibration, str):
        calibration = json.loads(calibration)
    metadata = row["metadata"]
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    location = row["location"]
    if not isinstance(location, BaseGeometry):
        location = Point(0.0, 0.0)
    return SensorDevice(
        id=row["id"],
        device_type=row["device_type"],
        cell_id=row["cell_id"],
        location=location,
        calibration=calibration or {},
        status=row["status"],
        last_seen_at=row["last_seen_at"],
        metadata=metadata or {},
        livello=row["livello"],
    )


async def chiave_pubblica(device_id: str) -> bytes | None:
    """La chiave che firma l'ingresso HTTP (#265); ``None`` senza dispositivo o
    senza chiave, che per chi chiede sono la stessa cosa: una firma che non si
    può verificare."""
    async with acquire() as conn:
        chiave: bytes | None = await conn.fetchval(
            "SELECT chiave_pubblica FROM sensor_devices WHERE id = $1", device_id
        )
    return chiave


async def touch_last_seen(device_id: str, *, at: datetime) -> None:
    """Bump ``last_seen_at`` (idempotent — no-op if device is missing)."""
    async with acquire() as conn:
        await conn.execute(
            """
            UPDATE sensor_devices
               SET last_seen_at = GREATEST(COALESCE(last_seen_at, $2), $2),
                   updated_at = now()
             WHERE id = $1
            """,
            device_id,
            at,
        )


async def stato_dal_dispositivo(device_id: str, status: Literal["online", "offline"]) -> None:
    """Lo stato che il dispositivo dichiara (LWT, #252): non toglie mai una
    quarantena, che decide Limen e non il dispositivo."""
    async with acquire() as conn:
        await conn.execute(
            """
            UPDATE sensor_devices SET status = $2, updated_at = now()
             WHERE id = $1 AND status <> 'quarantined'
            """,
            device_id,
            status,
        )


async def set_status(device_id: str, status: SensorStatus) -> None:
    async with acquire() as conn:
        await conn.execute(
            "UPDATE sensor_devices SET status = $2, updated_at = now() WHERE id = $1",
            device_id,
            status,
        )


@dataclass(frozen=True, slots=True)
class StazionePubblica:
    """Ciò che di un dispositivo si può mostrare a chiunque (#255).

    Mai la posizione esatta di una stazione di terzi, mai chi l'ha
    registrata: la query arrotonda e non legge ``registrante_id``.
    """

    id: str
    device_type: str
    livello: SensorLivello
    status: SensorStatus
    lon: float
    lat: float
    arrotondata: bool
    grandezze: tuple[str, ...]
    ultima_grandezza: str | None
    ultimo_valore: float | None
    ultima_unita: str | None
    ultimo_istante: datetime | None
    valide_24h: int
    segnalate_24h: int


# La guida (`#/sensori`, «Dati personali») promette 0,01°, circa un
# chilometro, per ogni stazione che non sia di un ente.
_STAZIONI_SQL = """
SELECT d.id, d.device_type, d.livello, d.status,
       (d.livello < 2 OR d.registrante_id IS NOT NULL) AS arrotondata,
       CASE WHEN d.livello < 2 OR d.registrante_id IS NOT NULL
            THEN round(ST_X(d.location)::numeric, 2)::double precision
            ELSE ST_X(d.location) END AS lon,
       CASE WHEN d.livello < 2 OR d.registrante_id IS NOT NULL
            THEN round(ST_Y(d.location)::numeric, 2)::double precision
            ELSE ST_Y(d.location) END AS lat,
       COALESCE(g.grandezze, '{}') AS grandezze,
       u.observed_property, u.result_value, u.result_unit, u.phenomenon_time,
       COALESCE(q.valide, 0) AS valide, COALESCE(q.segnalate, 0) AS segnalate
FROM sensor_devices d
-- Le grandezze dalle ultime 500 righe, non da trenta giorni: con l'indice
-- (device_id, phenomenon_time) sono 500 letture per stazione invece di
-- decine di migliaia.
LEFT JOIN LATERAL (
    SELECT array_agg(DISTINCT x.observed_property ORDER BY x.observed_property) AS grandezze
    FROM (
        SELECT o.observed_property
        FROM sensor_observations o
        WHERE o.device_id = d.id AND o.phenomenon_time > now() - interval '30 days'
        ORDER BY o.phenomenon_time DESC
        LIMIT 500
    ) x
) g ON true
LEFT JOIN LATERAL (
    -- Un picco scartato dal QC non è «l'ultimo dato».
    SELECT o.observed_property, o.result_value, o.result_unit, o.phenomenon_time
    FROM sensor_observations o
    WHERE o.device_id = d.id AND o.phenomenon_time > now() - interval '30 days'
      AND o.quality = 'ok'
    ORDER BY o.phenomenon_time DESC
    LIMIT 1
) u ON true
LEFT JOIN LATERAL (
    SELECT count(*) FILTER (WHERE o.quality = 'ok') AS valide,
           count(*) FILTER (WHERE o.quality <> 'ok') AS segnalate
    FROM sensor_observations o
    WHERE o.device_id = d.id AND o.phenomenon_time > now() - interval '24 hours'
) q ON true
-- In quarantena c'è anche ciò che `limen sensore cancella-registrante` ha
-- revocato: la guida promette che non resta nulla che lo colleghi a chi lo
-- aveva, e l'id l'aveva scelto lui.
WHERE d.status <> 'quarantined'
ORDER BY d.id
"""


async def stazioni_pubbliche() -> list[StazionePubblica]:
    async with acquire() as conn:
        rows = await conn.fetch(_STAZIONI_SQL)
    return [
        StazionePubblica(
            id=r["id"],
            device_type=r["device_type"],
            livello=r["livello"],
            status=r["status"],
            lon=r["lon"],
            lat=r["lat"],
            arrotondata=r["arrotondata"],
            grandezze=tuple(r["grandezze"]),
            ultima_grandezza=r["observed_property"],
            ultimo_valore=r["result_value"],
            ultima_unita=r["result_unit"],
            ultimo_istante=r["phenomenon_time"],
            valide_24h=r["valide"],
            segnalate_24h=r["segnalate"],
        )
        for r in rows
    ]


__all__ = [
    "LIVELLO_SCORING",
    "SensorDevice",
    "SensorLivello",
    "SensorStatus",
    "StazionePubblica",
    "chiave_pubblica",
    "get_device",
    "set_status",
    "stato_dal_dispositivo",
    "stazioni_pubbliche",
    "touch_last_seen",
    "upsert_many",
]
