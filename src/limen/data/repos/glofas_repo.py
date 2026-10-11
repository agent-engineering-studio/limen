"""La portata ordinaria per nodo GloFAS — migrazione 068 (#200)."""

from __future__ import annotations

from limen.data.db import acquire

Nodo = tuple[float, float]


async def riferimenti(
    nodes: list[Nodo], *, percentile: float, window_days: int
) -> dict[Nodo, float | None]:
    """I riferimenti già calcolati per ``nodes``; un nodo assente non è ancora calcolato."""
    if not nodes:
        return {}
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT r.node_lon, r.node_lat, r.portata
            FROM glofas_riferimento r
            JOIN unnest($1::numeric[], $2::numeric[]) AS n(lon, lat)
              ON r.node_lon = round(n.lon, 4) AND r.node_lat = round(n.lat, 4)
            WHERE r.percentile = $3 AND r.window_days = $4
            """,
            [lon for lon, _ in nodes],
            [lat for _, lat in nodes],
            percentile,
            window_days,
        )
    letti = {
        (float(r["node_lon"]), float(r["node_lat"])): (
            float(r["portata"]) if r["portata"] is not None else None
        )
        for r in rows
    }
    out: dict[Nodo, float | None] = {}
    for n in nodes:
        chiave = (round(n[0], 4), round(n[1], 4))
        if chiave in letti:
            out[n] = letti[chiave]
    return out


async def salva(
    righe: list[tuple[Nodo, float | None]], *, percentile: float, window_days: int
) -> int:
    """Scrive o aggiorna i riferimenti calcolati. Rilanciabile."""
    if not righe:
        return 0
    async with acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO glofas_riferimento (node_lon, node_lat, percentile, window_days, portata)
            VALUES (round($1::numeric, 4), round($2::numeric, 4), $3, $4, $5)
            ON CONFLICT (node_lon, node_lat, percentile, window_days)
            DO UPDATE SET portata = EXCLUDED.portata, calcolato = now()
            """,
            [(lon, lat, percentile, window_days, portata) for (lon, lat), portata in righe],
        )
    return len(righe)


async def da_calcolare(
    *, spacing: float, percentile: float, window_days: int, limite: int
) -> list[Nodo]:
    """I nodi che servono e non hanno ancora un riferimento, i più pesanti prima.

    Solo i nodi più vicini a celle mappate nella Mosaicatura ISPRA: fuori mappa
    la suscettibilità è il valore di ripiego, e ripiego per fluviale non arriva
    mai sopra la classe bassa. Prima i nodi con più suscettibilità sotto, così
    le prime notti coprono i fiumi che contano.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            WITH nodi AS (
                SELECT round(round(ST_X(g.centroid)::numeric / $1) * $1, 4) AS lon,
                       round(round(ST_Y(g.centroid)::numeric / $1) * $1, 4) AS lat,
                       sum(f.flood_hazard_norm) AS peso
                FROM cell_static_factors f
                JOIN grid_cells g ON g.id = f.cell_id
                WHERE f.flood_hazard_norm IS NOT NULL
                GROUP BY 1, 2
            )
            SELECT n.lon, n.lat
            FROM nodi n
            LEFT JOIN glofas_riferimento r
              ON r.node_lon = n.lon AND r.node_lat = n.lat
             AND r.percentile = $2 AND r.window_days = $3
            WHERE r.node_lon IS NULL
            ORDER BY n.peso DESC, n.lon, n.lat
            LIMIT $4
            """,
            spacing,
            percentile,
            window_days,
            limite,
        )
    return [(float(r["lon"]), float(r["lat"])) for r in rows]
