"""Rollup comunale degli alert, coda del digest e contatori per canale (#59).

Tre letture e tre scritture, tutte piccole. La parte decidibile — come
raggruppare, se spedire o accodare, come scrivere il testo — sta in
:mod:`limen.notifications.governance`, che non fa I/O ed è provabile da sola.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime, timedelta

from limen.core.logging import get_logger
from limen.core.models.hazard import DEFAULT_HAZARD, HazardType
from limen.core.models.risk import RiskLevel
from limen.data.db import acquire
from limen.notifications.governance import ComuneAggregate

log = get_logger(__name__)


async def insert_aggregates(
    aggregates: Iterable[ComuneAggregate],
    *,
    state: str,
    channels: dict[str, bool] | None = None,
    digest_id: str | None = None,
) -> list[int]:
    """Scrive il rollup. ``state`` è ``'sent'`` o ``'queued'``.

    Ritorna gli id, perché chi accoda deve poter marcare esattamente quelle
    righe quando il digest le spedisce — e non "tutte le righe accodate", che
    includerebbe quelle arrivate nel frattempo.
    """
    items = list(aggregates)
    if not items:
        return []
    payload = json.dumps(channels or {}, default=str)
    ids: list[int] = []
    async with acquire() as conn, conn.transaction():
        for a in items:
            row = await conn.fetchrow(
                """
                INSERT INTO alert_aggregates (
                    istat_code, comune, aoi_id, hazard_type, max_level,
                    max_score, cells_count, top_cells, state, sent_at,
                    digest_id, channels
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9,
                    CASE WHEN $9 = 'sent' THEN now() ELSE NULL END,
                    $10, $11::jsonb
                )
                RETURNING id
                """,
                a.istat_code,
                a.comune,
                a.aoi_id,
                a.hazard.value,
                a.max_level.value,
                a.max_score,
                a.cells_count,
                json.dumps(
                    [
                        {"cell_id": cid, "score": score, "level": level.value}
                        for cid, score, level in a.top_cells
                    ]
                ),
                state,
                digest_id,
                payload,
            )
            if row is not None:
                ids.append(int(row["id"]))
    log.info("alert_aggregates.insert", count=len(items), state=state)
    return ids


async def comuni_alerted_within(
    istat_codes: Iterable[str],
    *,
    window: timedelta,
    hazard: HazardType = DEFAULT_HAZARD,
    now: datetime | None = None,
) -> set[str]:
    """I comuni già allertati per questo pericolo dentro la finestra.

    La dedup per cella non basta a un destinatario umano: due celle vicine
    dello stesso paese sono lo stesso avviso ricevuto due volte. Resta per
    pericolo, però — un'allerta frana non deve zittire un'allerta alluvione
    sullo stesso comune.
    """
    codes = [c for c in istat_codes if c]
    if not codes or window.total_seconds() <= 0:
        return set()
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT istat_code
            FROM alert_aggregates
            WHERE istat_code = ANY($1::text[])
              AND hazard_type = $4
              AND state = 'sent'
              AND created_at >= COALESCE($2, now()) - $3::interval
            """,
            codes,
            now,
            window,
            hazard.value,
        )
    return {str(r["istat_code"]) for r in rows}


async def comuni_queued(
    istat_codes: Iterable[str], *, hazard: HazardType = DEFAULT_HAZARD
) -> set[str]:
    """I comuni che hanno già una voce **in coda** per questo pericolo.

    Serve prima di accodare, e non è la stessa domanda di
    :func:`comuni_alerted_within`. Un ciclo trattenuto non scrive in
    `alert_dispatches` — non è uscito niente, e registrarlo come spedito
    sopprimerebbe un avviso che nessuno ha ricevuto — quindi il ciclo
    successivo ritrova le stesse celle sopra soglia. Senza questo controllo lo
    stesso comune finirebbe in coda una volta per ciclo, e il riepilogo lo
    nominerebbe N volte con lo stesso numero.

    Senza finestra: la coda ha già la sua scadenza (`digest_max_age_minutes`),
    e ciò che è ancora `queued` è per definizione ancora in attesa.
    """
    codes = [c for c in istat_codes if c]
    if not codes:
        return set()
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT istat_code
            FROM alert_aggregates
            WHERE istat_code = ANY($1::text[])
              AND hazard_type = $2
              AND state = 'queued'
            """,
            codes,
            hazard.value,
        )
    return {str(r["istat_code"]) for r in rows}


async def sends_last_hour(channel: str, *, now: datetime | None = None) -> int:
    """Quante uscite riuscite ha avuto questo canale nell'ultima ora.

    Solo quelle riuscite: un invio fallito non ha consumato l'attenzione di
    nessuno, e contarlo nel limite farebbe tacere il sistema proprio quando
    un canale è rotto.
    """
    async with acquire() as conn:
        n = await conn.fetchval(
            """
            SELECT count(*) FROM notification_sends
            WHERE channel = $1 AND ok
              AND sent_at >= COALESCE($2, now()) - interval '1 hour'
            """,
            channel,
            now,
        )
    return int(n or 0)


async def record_sends(outcomes: dict[str, bool], *, kind: str, aggregates: int) -> int:
    """Un record per canale per messaggio uscito."""
    if not outcomes:
        return 0
    async with acquire() as conn, conn.transaction():
        for channel, ok in outcomes.items():
            await conn.execute(
                """
                INSERT INTO notification_sends (channel, kind, ok, aggregates)
                VALUES ($1, $2, $3, $4)
                """,
                channel,
                kind,
                bool(ok),
                aggregates,
            )
    return len(outcomes)


async def fetch_queued(
    *, max_age: timedelta, now: datetime | None = None
) -> tuple[list[int], list[ComuneAggregate]]:
    """La coda ancora spedibile, e gli id per marcarla.

    Le voci più vecchie di ``max_age`` non vengono restituite: un riepilogo di
    allerte di ieri non è un ritardo, è disinformazione. Chi chiama le scade
    con :func:`expire_stale`.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, istat_code, comune, aoi_id, hazard_type, max_level,
                   max_score, cells_count, top_cells
            FROM alert_aggregates
            WHERE state = 'queued'
              AND created_at >= COALESCE($1, now()) - $2::interval
            ORDER BY created_at, id
            """,
            now,
            max_age,
        )
    ids: list[int] = []
    out: list[ComuneAggregate] = []
    for r in rows:
        ids.append(int(r["id"]))
        top = r["top_cells"]
        if isinstance(top, str):
            top = json.loads(top)
        out.append(
            ComuneAggregate(
                istat_code=r["istat_code"],
                comune=r["comune"],
                aoi_id=str(r["aoi_id"]),
                hazard=HazardType(r["hazard_type"]),
                max_level=RiskLevel(r["max_level"]),
                max_score=float(r["max_score"]),
                cells_count=int(r["cells_count"]),
                top_cells=tuple(
                    (str(c["cell_id"]), float(c["score"]), RiskLevel(c["level"]))
                    for c in (top or [])
                ),
            )
        )
    return ids, out


async def mark_sent(ids: Iterable[int], *, digest_id: str, channels: dict[str, bool]) -> int:
    """Marca come spedite le righe che il digest ha appena mandato."""
    id_list = list(ids)
    if not id_list:
        return 0
    async with acquire() as conn:
        await conn.execute(
            """
            UPDATE alert_aggregates
               SET state = 'sent', sent_at = now(),
                   digest_id = $2, channels = $3::jsonb
             WHERE id = ANY($1::bigint[])
            """,
            id_list,
            digest_id,
            json.dumps(channels, default=str),
        )
    return len(id_list)


async def expire_stale(*, max_age: timedelta, now: datetime | None = None) -> int:
    """Scade le voci in coda troppo vecchie per essere ancora vere."""
    async with acquire() as conn:
        status = await conn.execute(
            """
            UPDATE alert_aggregates SET state = 'expired'
             WHERE state = 'queued'
               AND created_at < COALESCE($1, now()) - $2::interval
            """,
            now,
            max_age,
        )
    # asyncpg ritorna "UPDATE <n>".
    removed = int(status.split()[-1]) if status else 0
    if removed:
        log.info("alert_aggregates.expired", count=removed)
    return removed


async def sample_recent(
    *, limit: int, since: timedelta, now: datetime | None = None
) -> list[dict[str, object]]:
    """Campione casuale di alert recenti, per la review manuale del FAR.

    Casuale e non "i più recenti": i più recenti sono correlati fra loro (uno
    stesso evento meteo), e un campione correlato non misura il tasso di falsi
    positivi, misura un temporale.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, istat_code, comune, aoi_id, hazard_type, max_level,
                   max_score, cells_count, top_cells, state, created_at,
                   sent_at, digest_id
            FROM alert_aggregates
            WHERE created_at >= COALESCE($2, now()) - $3::interval
            ORDER BY random()
            LIMIT $1
            """,
            limit,
            now,
            since,
        )
    out: list[dict[str, object]] = []
    for r in rows:
        top = r["top_cells"]
        if isinstance(top, str):
            top = json.loads(top)
        out.append(
            {
                "id": int(r["id"]),
                "istat_code": r["istat_code"],
                "comune": r["comune"],
                "aoi_id": str(r["aoi_id"]),
                "hazard_type": str(r["hazard_type"]),
                "max_level": str(r["max_level"]),
                "max_score": float(r["max_score"]),
                "cells_count": int(r["cells_count"]),
                "top_cells": top or [],
                "state": str(r["state"]),
                "created_at": r["created_at"],
                "sent_at": r["sent_at"],
                "digest_id": r["digest_id"],
            }
        )
    return out


__all__ = [
    "comuni_alerted_within",
    "comuni_queued",
    "expire_stale",
    "fetch_queued",
    "insert_aggregates",
    "mark_sent",
    "record_sends",
    "sample_recent",
    "sends_last_hour",
]
