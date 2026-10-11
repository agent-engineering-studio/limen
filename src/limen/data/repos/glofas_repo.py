"""La portata ordinaria per nodo GloFAS — migrazione 068 (#200)."""

from __future__ import annotations

from datetime import date, timedelta

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
    righe: list[tuple[Nodo, float | None]],
    *,
    percentile: float,
    window_days: int,
    fonte: str = "open-meteo",
) -> int:
    """Scrive o aggiorna i riferimenti calcolati. Rilanciabile."""
    if not righe:
        return 0
    async with acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO glofas_riferimento
                (node_lon, node_lat, percentile, window_days, portata, fonte)
            VALUES (round($1::numeric, 4), round($2::numeric, 4), $3, $4, $5, $6)
            ON CONFLICT (node_lon, node_lat, percentile, window_days)
            DO UPDATE SET portata = EXCLUDED.portata, fonte = EXCLUDED.fonte, calcolato = now()
            """,
            [(lon, lat, percentile, window_days, portata, fonte) for (lon, lat), portata in righe],
        )
    return len(righe)


async def da_calcolare(
    *, spacing: float, percentile: float, window_days: int, limite: int, soglia_pioggia_mm: float
) -> list[Nodo]:
    """I nodi che servono e non hanno ancora un riferimento, i più urgenti prima.

    Solo i nodi più vicini a celle mappate nella Mosaicatura ISPRA: fuori mappa
    la suscettibilità è il valore di ripiego, e ripiego per fluviale non arriva
    mai sopra la classe bassa. L'ordine:

    1. dove la previsione dà pioggia sopra la soglia pluviale nei prossimi tre
       giorni (`latest_forecast_comune`): lì il riferimento serve stanotte;
    2. la suscettibilità **pesata per l'esposizione** delle celle: a parità di
       area allagabile, prima il fiume che passa vicino a case e strade.
       Misurato sui 3.366 nodi: i primi 340 coprono il 30 % del rischio esposto
       contro il 18 % dell'ordine per sola suscettibilità;
    3. la suscettibilità, per i nodi senza esposizione.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            WITH celle AS (
                SELECT g.id,
                       round(round(ST_X(g.centroid)::numeric / $1) * $1, 4) AS lon,
                       round(round(ST_Y(g.centroid)::numeric / $1) * $1, 4) AS lat,
                       f.flood_hazard_norm AS h,
                       coalesce(f.exposure_norm, 0) AS e
                FROM cell_static_factors f
                JOIN grid_cells g ON g.id = f.cell_id
                WHERE f.flood_hazard_norm IS NOT NULL
            ),
            pioggia AS (
                SELECT cc.cell_id, max(l.rain_mm) AS mm
                FROM cell_comune_tutte cc
                JOIN latest_forecast_comune l
                  ON l.istat_code = cc.istat_code AND l.hazard_type = 'flood'
                GROUP BY cc.cell_id
            ),
            nodi AS (
                SELECT c.lon, c.lat,
                       sum(c.h) AS peso,
                       sum(c.h * c.e) AS esposto,
                       coalesce(max(p.mm), 0) >= $5 AS piove
                FROM celle c
                LEFT JOIN pioggia p ON p.cell_id = c.id
                GROUP BY c.lon, c.lat
            )
            SELECT n.lon, n.lat
            FROM nodi n
            LEFT JOIN glofas_riferimento r
              ON r.node_lon = n.lon AND r.node_lat = n.lat
             AND r.percentile = $2 AND r.window_days = $3
            WHERE r.node_lon IS NULL
            ORDER BY n.piove DESC, n.esposto DESC, n.peso DESC, n.lon, n.lat
            LIMIT $4
            """,
            spacing,
            percentile,
            window_days,
            limite,
            soglia_pioggia_mm,
        )
    return [(float(r["lon"]), float(r["lat"])) for r in rows]


async def con_fiume(*, percentile: float, window_days: int) -> int:
    """Quanti nodi hanno un fiume: sono quelli di cui lo sweep chiede la previsione."""
    async with acquire() as conn:
        n = await conn.fetchval(
            """
            SELECT count(*) FROM glofas_riferimento
            WHERE percentile = $1 AND window_days = $2 AND portata > 0
            """,
            percentile,
            window_days,
        )
    return int(n or 0)


async def nodi_con_fiume(*, percentile: float, window_days: int) -> list[Nodo]:
    """I nodi con un fiume: quelli di cui serve la previsione di portata."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT node_lon, node_lat FROM glofas_riferimento
            WHERE percentile = $1 AND window_days = $2 AND portata > 0
            ORDER BY node_lon, node_lat
            """,
            percentile,
            window_days,
        )
    return [(float(r["node_lon"]), float(r["node_lat"])) for r in rows]


async def ultima_corsa() -> date | None:
    """La corsa di previsione più recente salvata, se ce n'è una."""
    async with acquire() as conn:
        corsa = await conn.fetchval("SELECT max(corsa) FROM glofas_previsione")
    return corsa if isinstance(corsa, date) else None


#: Le corse più vecchie si cancellano a ogni salvataggio: lo sweep legge solo
#: l'ultima, e una settimana basta a ricostruire un caso dopo il fatto.
_CORSE_TENUTE_GIORNI = 7


async def salva_previsione(corsa: date, picchi: dict[Nodo, float], *, fonte: str) -> int:
    """Scrive i picchi di una corsa. Rilanciabile."""
    if not picchi:
        return 0
    async with acquire() as conn, conn.transaction():
        await conn.executemany(
            """
            INSERT INTO glofas_previsione (node_lon, node_lat, corsa, picco, fonte)
            VALUES (round($1::numeric, 4), round($2::numeric, 4), $3, $4, $5)
            ON CONFLICT (node_lon, node_lat, corsa)
            DO UPDATE SET picco = EXCLUDED.picco, fonte = EXCLUDED.fonte, scaricato = now()
            """,
            [(lon, lat, corsa, picco, fonte) for (lon, lat), picco in picchi.items()],
        )
        await conn.execute(
            "DELETE FROM glofas_previsione WHERE corsa < $1",
            corsa - timedelta(days=_CORSE_TENUTE_GIORNI),
        )
    return len(picchi)


async def picchi(nodes: list[Nodo], *, dal: date) -> dict[Nodo, float] | None:
    """Il picco previsto per ``nodes`` dall'ultima corsa non più vecchia di ``dal``.

    ``None`` se non c'è una corsa abbastanza recente: chi chiama torna alla
    fonte di prima. Un dizionario, anche vuoto, vuol dire che la corsa c'è, e
    un nodo che manca non ha previsione.
    """
    async with acquire() as conn:
        corsa = await conn.fetchval(
            "SELECT max(corsa) FROM glofas_previsione WHERE corsa >= $1", dal
        )
        if corsa is None or not nodes:
            return None if corsa is None else {}
        rows = await conn.fetch(
            """
            SELECT p.node_lon, p.node_lat, p.picco
            FROM glofas_previsione p
            JOIN unnest($1::numeric[], $2::numeric[]) AS n(lon, lat)
              ON p.node_lon = round(n.lon, 4) AND p.node_lat = round(n.lat, 4)
            WHERE p.corsa = $3
            """,
            [lon for lon, _ in nodes],
            [lat for _, lat in nodes],
            corsa,
        )
    letti = {(float(r["node_lon"]), float(r["node_lat"])): float(r["picco"]) for r in rows}
    out: dict[Nodo, float] = {}
    for n in nodes:
        chiave = (round(n[0], 4), round(n[1], 4))
        if chiave in letti:
            out[n] = letti[chiave]
    return out
