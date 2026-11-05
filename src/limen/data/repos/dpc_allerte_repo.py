"""Le allerte ufficiali DPC (migrazione 063): scrittura e lettura per comune."""

from __future__ import annotations

from typing import Any

from dpc_radar.bulletins import Bulletin

from limen.data.db import acquire

_UPSERT_SQL = """
INSERT INTO dpc_allerte (
    valido, zona, bollettino, emesso, livello, idrogeologico, idraulico, temporali, geom
) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
ON CONFLICT (valido, zona) DO UPDATE SET
    bollettino = EXCLUDED.bollettino,
    emesso = EXCLUDED.emesso,
    livello = EXCLUDED.livello,
    idrogeologico = EXCLUDED.idrogeologico,
    idraulico = EXCLUDED.idraulico,
    temporali = EXCLUDED.temporali,
    geom = EXCLUDED.geom
-- Un bollettino più vecchio non sovrascrive un «Aggiornamento» dello stesso
-- giorno arrivato dopo.
WHERE dpc_allerte.emesso <= EXCLUDED.emesso
"""


async def scrivi(b: Bulletin) -> int:
    async with acquire() as conn, conn.transaction():
        await conn.executemany(
            _UPSERT_SQL,
            [
                (
                    z.valid,
                    z.name,
                    b.name,
                    b.issued,
                    z.level,
                    z.hydrogeological,
                    z.hydraulic,
                    z.thunderstorms,
                    z.geometry,
                )
                for z in b.zones
            ],
        )
    return len(b.zones)


#: Per comune, la zona che contiene il suo punto interno, per oggi e domani
#: (ora italiana). Un comune a cavallo di due zone prende quella del suo
#: punto interno: è la stessa regola con cui ha un centroide.
_PER_COMUNE_SQL = """
SELECT c.istat_code, a.valido, a.zona, a.emesso, a.livello,
       a.idrogeologico, a.idraulico, a.temporali,
       a.valido = (now() AT TIME ZONE 'Europe/Rome')::date AS e_oggi
FROM comuni c
JOIN dpc_allerte a ON ST_Intersects(a.geom, c.centroid)
WHERE c.istat_code = ANY($1::text[])
  AND a.valido BETWEEN (now() AT TIME ZONE 'Europe/Rome')::date
                   AND (now() AT TIME ZONE 'Europe/Rome')::date + 1
"""


async def per_comuni(conn: Any, istat_codes: list[str]) -> dict[str, dict[str, Any]]:
    """``{istat: {zona, emesso, oggi?, domani?}}``; un comune senza riga manca."""
    if not istat_codes:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for r in await conn.fetch(_PER_COMUNE_SQL, istat_codes):
        voce = out.setdefault(str(r["istat_code"]), {"zona": r["zona"], "emesso": r["emesso"]})
        voce["oggi" if r["e_oggi"] else "domani"] = {
            "valido": r["valido"],
            "livello": int(r["livello"]),
            "idrogeologico": int(r["idrogeologico"]),
            "idraulico": int(r["idraulico"]),
            "temporali": int(r["temporali"]),
        }
    return out
