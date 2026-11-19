"""``radar_piogge_rare``: i candidati del catalogo radar delle piogge rare (#643, migr. 096)."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from dpc_radar import Event

from limen.data.db import acquire


async def salva(giorno: date, eventi: list[Event]) -> int:
    """Gli eventi che finiscono nel giorno (UTC) prendono il posto di quelli di prima.

    Idempotente: rifatto la notte dopo su un archivio più completo, un evento
    può cambiare ora o punto, e non resta il doppione di prima. Il comune è
    quello che contiene il punto più raro (NULL in mare o fuori Italia).
    """
    inizio = datetime.combine(giorno, time(), UTC)
    async with acquire() as conn, conn.transaction():
        await conn.execute(
            "DELETE FROM radar_piogge_rare WHERE evento_at > $1 AND evento_at <= $2",
            inizio,
            inizio + timedelta(days=1),
        )
        await conn.executemany(
            """
            INSERT INTO radar_piogge_rare (
                evento_at, finestra_ore, lon, lat, mm, livello_mm, ritorno_anni,
                primo_at, ultimo_at, area_km2, bbox, radar_mm, merging_mm, confermato,
                istat_code
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14,
                    (SELECT istat_code FROM comuni
                     WHERE ST_Covers(geom, ST_SetSRID(ST_MakePoint($3, $4), 4326))
                     LIMIT 1))
            ON CONFLICT (evento_at, lon, lat) DO UPDATE SET
                finestra_ore = EXCLUDED.finestra_ore, mm = EXCLUDED.mm,
                livello_mm = EXCLUDED.livello_mm, ritorno_anni = EXCLUDED.ritorno_anni,
                primo_at = EXCLUDED.primo_at, ultimo_at = EXCLUDED.ultimo_at,
                area_km2 = EXCLUDED.area_km2, bbox = EXCLUDED.bbox,
                radar_mm = EXCLUDED.radar_mm, merging_mm = EXCLUDED.merging_mm,
                confermato = EXCLUDED.confermato, istat_code = EXCLUDED.istat_code,
                trovato_at = now()
            """,
            [
                (
                    e.time,
                    e.window,
                    round(e.lon, 4),
                    round(e.lat, 4),
                    e.mm,
                    e.level_mm,
                    e.return_period,
                    e.first,
                    e.last,
                    e.area_km2,
                    list(e.bbox),
                    e.radar_mm,
                    e.merging_mm,
                    e.confirmed,
                )
                for e in eventi
            ],
        )
    return len(eventi)


async def comuni_recenti(dal: datetime, massimi: int) -> list[str]:
    """I comuni con una pioggia rara confermata dal «Merging» da ``dal``, la più rara prima."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT c.name
            FROM radar_piogge_rare r JOIN comuni c USING (istat_code)
            WHERE r.evento_at >= $1 AND r.confermato
            GROUP BY c.name
            ORDER BY max(r.mm / r.livello_mm) DESC
            LIMIT $2
            """,
            dal,
            massimi,
        )
    return [str(r["name"]) for r in rows]
