"""``radar_temporali``: i temporali dell'ultimo SRI e dove vanno (#643, migrazione 095)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from limen.data.db import acquire


@dataclass(frozen=True, slots=True)
class Temporale:
    osservato_at: datetime
    n: int
    soglia_mmh: float
    lon: float
    lat: float
    area_km2: float
    picco_mmh: float
    media_mmh: float
    picco_lon: float
    picco_lat: float
    bbox: tuple[float, float, float, float]
    velocita_kmh: float | None
    direzione_gradi: float | None


_COLONNE = (
    "osservato_at, n, soglia_mmh, lon, lat, area_km2, picco_mmh, media_mmh, "
    "picco_lon, picco_lat, bbox, velocita_kmh, direzione_gradi"
)


async def sostituisci(temporali: list[Temporale]) -> None:
    """Lo stato di adesso: le righe del giro prima se ne vanno, anche se ora non c'è niente."""
    async with acquire() as conn, conn.transaction():
        await conn.execute("DELETE FROM radar_temporali")
        await conn.executemany(
            f"INSERT INTO radar_temporali ({_COLONNE}) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)",
            [
                (
                    t.osservato_at,
                    t.n,
                    t.soglia_mmh,
                    t.lon,
                    t.lat,
                    t.area_km2,
                    t.picco_mmh,
                    t.media_mmh,
                    t.picco_lon,
                    t.picco_lat,
                    list(t.bbox),
                    t.velocita_kmh,
                    t.direzione_gradi,
                )
                for t in temporali
            ],
        )


async def leggi(eta_massima: timedelta) -> list[Temporale]:
    """I temporali di adesso; nessuno se l'ultimo giro è più vecchio di ``eta_massima``.

    Una sveglia che non legge più il radar lascerebbe in tabella i temporali di
    ore prima, e la mappa li direbbe «adesso».
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            f"SELECT {_COLONNE} FROM radar_temporali "
            "WHERE osservato_at >= now() - $1::interval ORDER BY n",
            eta_massima,
        )
    return [
        Temporale(
            osservato_at=r["osservato_at"],
            n=r["n"],
            soglia_mmh=r["soglia_mmh"],
            lon=r["lon"],
            lat=r["lat"],
            area_km2=r["area_km2"],
            picco_mmh=r["picco_mmh"],
            media_mmh=r["media_mmh"],
            picco_lon=r["picco_lon"],
            picco_lat=r["picco_lat"],
            bbox=(r["bbox"][0], r["bbox"][1], r["bbox"][2], r["bbox"][3]),
            velocita_kmh=r["velocita_kmh"],
            direzione_gradi=r["direzione_gradi"],
        )
        for r in rows
    ]
