"""Le zone franose a cui Limen lega la pioggia dei pluviometri: una cella, o le
celle di un comune in un'area PAI o vicine a una frana IFFI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from limen.data.db import acquire

#: Distanza dalla frana IFFI più vicina entro cui una cella è franosa.
IFFI_VICINA_M = 500.0
_CELLE_COMUNE = 200


@dataclass(frozen=True, slots=True)
class CellaZona:
    cell_id: str
    aoi_id: str
    lon: float
    lat: float
    pai_class_norm: float | None
    iffi_density_500: float | None
    distance_to_iffi_m: float | None
    s_static: float | None

    @property
    def franosa(self) -> bool:
        return bool(self.pai_class_norm) or (
            self.distance_to_iffi_m is not None and self.distance_to_iffi_m <= IFFI_VICINA_M
        )

    @property
    def senza_fattori(self) -> bool:
        """PAI e IFFI non caricati: non si sa se è franosa, che non vuol dire che non lo sia."""
        return self.pai_class_norm is None and self.distance_to_iffi_m is None


@dataclass(frozen=True, slots=True)
class Zona:
    aoi_id: str | None
    #: La cella chiesta, o le celle franose del comune (le più suscettibili prima).
    celle: list[CellaZona]
    #: Le celle del comune (1 per una cella) e quante non hanno PAI né IFFI caricati.
    celle_totali: int
    celle_senza_fattori: int


_COLONNE = """
    g.id, g.aoi_id, ST_X(g.centroid) AS lon, ST_Y(g.centroid) AS lat,
    f.pai_class_norm, f.iffi_density_500, f.distance_to_iffi_m, f.s_static
"""


def _cella(r: Any) -> CellaZona:
    return CellaZona(
        cell_id=r["id"],
        aoi_id=r["aoi_id"],
        lon=float(r["lon"]),
        lat=float(r["lat"]),
        pai_class_norm=r["pai_class_norm"],
        iffi_density_500=r["iffi_density_500"],
        distance_to_iffi_m=r["distance_to_iffi_m"],
        s_static=r["s_static"],
    )


async def zona(cell_id: str | None, istat_code: str | None) -> Zona | None:
    """``None`` se la cella o il comune non esistono."""
    async with acquire() as conn:
        if cell_id is not None:
            r = await conn.fetchrow(
                f"SELECT {_COLONNE} FROM grid_cells g "
                "LEFT JOIN cell_static_factors f ON f.cell_id = g.id WHERE g.id = $1",
                cell_id,
            )
            if r is None:
                return None
            c = _cella(r)
            return Zona(c.aoi_id, [c], 1, int(c.senza_fattori))
        comune = await conn.fetchrow(
            """
            SELECT c.aoi_id, count(cc.cell_id) AS totali,
                   count(cc.cell_id) FILTER (
                       WHERE f.pai_class_norm IS NULL AND f.distance_to_iffi_m IS NULL
                   ) AS senza_fattori
              FROM comuni c
              LEFT JOIN cell_comune cc ON cc.istat_code = c.istat_code
              LEFT JOIN cell_static_factors f ON f.cell_id = cc.cell_id
             WHERE c.istat_code = $1
             GROUP BY c.aoi_id
            """,
            istat_code,
        )
        if comune is None:
            return None
        righe = await conn.fetch(
            f"""
            SELECT {_COLONNE} FROM cell_comune cc
              JOIN grid_cells g ON g.id = cc.cell_id
              JOIN cell_static_factors f ON f.cell_id = g.id
             WHERE cc.istat_code = $1
               AND (COALESCE(f.pai_class_norm, 0) > 0 OR f.distance_to_iffi_m <= $2)
             ORDER BY f.s_static DESC NULLS LAST
             LIMIT $3
            """,
            istat_code,
            IFFI_VICINA_M,
            _CELLE_COMUNE,
        )
    return Zona(
        comune["aoi_id"],
        [_cella(r) for r in righe],
        int(comune["totali"]),
        int(comune["senza_fattori"]),
    )


async def frane(
    cell_id: str | None, istat_code: str | None, dal: datetime, al: datetime, limite: int
) -> list[dict[str, Any]]:
    """Le frane datate della zona, le più recenti per prime."""
    sottozona = (
        "SELECT geom FROM grid_cells WHERE id = $1"
        if cell_id is not None
        else "SELECT geom FROM comuni WHERE istat_code = $1"
    )
    async with acquire() as conn:
        righe = await conn.fetch(
            f"""
            SELECT e.event_time, e.source, e.temporal_accuracy,
                   ST_X(ST_PointOnSurface(e.geom)) AS lon, ST_Y(ST_PointOnSurface(e.geom)) AS lat
              FROM landslide_events e, ({sottozona}) z
             WHERE ST_Intersects(e.geom, z.geom) AND e.event_time BETWEEN $2 AND $3
             ORDER BY e.event_time DESC
             LIMIT $4
            """,
            cell_id if cell_id is not None else istat_code,
            dal,
            al,
            limite,
        )
    return [dict(r) for r in righe]
