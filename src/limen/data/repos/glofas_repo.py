"""La portata ordinaria per nodo GloFAS — migrazione 068 (#200)."""

from __future__ import annotations

from datetime import date, timedelta

from limen.core.models.hazard import HazardType
from limen.core.piena import Piena, piena
from limen.data.db import acquire

Nodo = tuple[float, float]

#: La sola fonte dei riferimenti (#448): l'archivio di Open-Meteo, che dal 2024
#: è la catena di `forecast_v4`, la stessa della previsione al numeratore. La
#: rianalisi EWDS ha la mediana uguale (0,98) ma è più bassa in un nodo su
#: dieci, fino a un terzo in Calabria ionica, e lì alzerebbe il rapporto.
FONTE_RIFERIMENTO = "open-meteo"


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
            WHERE r.percentile = $3::numeric(4,3) AND r.window_days = $4
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
    fonte: str = FONTE_RIFERIMENTO,
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

    Un riferimento di un'altra fonte (le righe ``ewds:`` scritte da
    ``limen glofas-ewds`` prima della #448) conta come da rifare, ma dopo quelli
    che mancano: intanto resta, meglio di nessuno.

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
             AND r.percentile = $2::numeric(4,3) AND r.window_days = $3
            WHERE r.node_lon IS NULL OR r.fonte <> $6
            ORDER BY r.node_lon IS NULL DESC, n.piove DESC, n.esposto DESC, n.peso DESC,
                     n.lon, n.lat
            LIMIT $4
            """,
            spacing,
            percentile,
            window_days,
            limite,
            soglia_pioggia_mm,
            FONTE_RIFERIMENTO,
        )
    return [(float(r["lon"]), float(r["lat"])) for r in rows]


async def salvati(*, percentile: float, window_days: int, fonte: str) -> dict[Nodo, float]:
    """I riferimenti di ``fonte`` con un fiume (portata positiva), per nodo."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT node_lon, node_lat, portata FROM glofas_riferimento
            WHERE percentile = $1::numeric(4,3) AND window_days = $2 AND fonte = $3
              AND portata > 0
            ORDER BY node_lon, node_lat
            """,
            percentile,
            window_days,
            fonte,
        )
    return {(float(r["node_lon"]), float(r["node_lat"])): float(r["portata"]) for r in rows}


async def con_fiume(*, percentile: float, window_days: int) -> int:
    """Quanti nodi hanno un fiume: sono quelli di cui lo sweep chiede la previsione."""
    async with acquire() as conn:
        n = await conn.fetchval(
            """
            SELECT count(*) FROM glofas_riferimento
            WHERE percentile = $1::numeric(4,3) AND window_days = $2 AND portata > 0
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
            WHERE percentile = $1::numeric(4,3) AND window_days = $2 AND portata > 0
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


async def salva_previsione(
    corsa: date,
    picchi: dict[Nodo, float],
    *,
    fonte: str,
    giorni: dict[Nodo, date | None] | None = None,
) -> int:
    """Scrive i picchi di una corsa, con il giorno di ciascuno se noto. Rilanciabile."""
    if not picchi:
        return 0
    async with acquire() as conn, conn.transaction():
        await conn.executemany(
            """
            INSERT INTO glofas_previsione (node_lon, node_lat, corsa, picco, fonte, giorno_picco)
            VALUES (round($1::numeric, 4), round($2::numeric, 4), $3, $4, $5, $6)
            ON CONFLICT (node_lon, node_lat, corsa)
            DO UPDATE SET picco = EXCLUDED.picco, fonte = EXCLUDED.fonte,
                          giorno_picco = EXCLUDED.giorno_picco, scaricato = now()
            """,
            [
                (lon, lat, corsa, picco, fonte, (giorni or {}).get((lon, lat)))
                for (lon, lat), picco in picchi.items()
            ],
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


async def salva_soglie(
    soglie: dict[Nodo, tuple[float | None, float | None, float | None]], *, fonte: str
) -> int:
    """Le soglie dei periodi di ritorno 2/5/20 anni per nodo (#522). Rilanciabile."""
    if not soglie:
        return 0
    async with acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO glofas_soglie (node_lon, node_lat, rl2, rl5, rl20, fonte)
            VALUES (round($1::numeric, 4), round($2::numeric, 4), $3, $4, $5, $6)
            ON CONFLICT (node_lon, node_lat) DO UPDATE
            SET rl2 = EXCLUDED.rl2, rl5 = EXCLUDED.rl5, rl20 = EXCLUDED.rl20,
                fonte = EXCLUDED.fonte, calcolato = now()
            """,
            [(lon, lat, r2, r5, r20, fonte) for (lon, lat), (r2, r5, r20) in soglie.items()],
        )
    return len(soglie)


async def riferimento_e_soglie(
    nodo: Nodo, *, percentile: float, window_days: int
) -> tuple[float | None, dict[int, float | None]] | None:
    """Il q90 del nodo e le sue soglie 2/5/20; ``None`` se il nodo non ha soglie."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT s.rl2, s.rl5, s.rl20, r.portata
            FROM glofas_soglie s
            LEFT JOIN glofas_riferimento r
              ON r.node_lon = s.node_lon AND r.node_lat = s.node_lat
             AND r.percentile = $3::numeric(4,3) AND r.window_days = $4
            WHERE s.node_lon = round($1::numeric, 4) AND s.node_lat = round($2::numeric, 4)
            """,
            nodo[0],
            nodo[1],
            percentile,
            window_days,
        )
    if row is None:
        return None
    q90 = float(row["portata"]) if row["portata"] is not None else None
    return q90, {2: row["rl2"], 5: row["rl5"], 20: row["rl20"]}


async def nodo_della_cella(cell_id: str) -> Nodo | None:
    """Il nodo del ramo fluviale che la cella legge: il più vicino sul reticolo a 0,1°.

    Lo stesso che sceglie il motore (``build_snapped_nodes`` + ``nearest_node``
    in ``openmeteo/flood.py``), ricostruito dal centroide della cella.
    """
    from limen.integrations.openmeteo.flood import NODE_SPACING_DEG
    from limen.integrations.openmeteo.grid import build_snapped_nodes, nearest_node

    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT ST_X(ST_Centroid(geom)) AS lon, ST_Y(ST_Centroid(geom)) AS lat"
            " FROM grid_cells WHERE id = $1",
            cell_id,
        )
    if row is None:
        return None
    lon, lat = float(row["lon"]), float(row["lat"])
    d = NODE_SPACING_DEG
    nodi = build_snapped_nodes((lon - d, lat - d, lon + d, lat + d), spacing=d)
    return nodi[nearest_node(lon, lat, nodi)]


async def piena_della_cella(cell_id: str, rapporto: object) -> Piena | None:
    """La piena prevista della cella in periodi di ritorno (#522), o ``None``."""
    from limen.core.scoring.regional_thresholds import FloodThresholds, load_hazard_thresholds

    if not isinstance(rapporto, int | float) or isinstance(rapporto, bool):
        return None
    nodo = await nodo_della_cella(cell_id)
    if nodo is None:
        return None
    flood = load_hazard_thresholds(HazardType.FLOOD)
    assert isinstance(flood, FloodThresholds)
    letto = await riferimento_e_soglie(
        nodo,
        percentile=flood.fluvial.reference_percentile,
        window_days=flood.fluvial.reference_window_days,
    )
    if letto is None:
        return None
    q90, soglie = letto
    return piena(float(rapporto), q90, soglie, await ultimo_picco(nodo))


async def nodi_con_soglie() -> set[Nodo]:
    """I nodi di cui le soglie sono già state lette (anche se mascherate)."""
    async with acquire() as conn:
        rows = await conn.fetch("SELECT node_lon, node_lat FROM glofas_soglie")
    return {(float(r["node_lon"]), float(r["node_lat"])) for r in rows}


async def ultimo_picco(nodo: Nodo) -> tuple[float, date | None] | None:
    """Picco e giorno del picco del nodo nella corsa più recente salvata."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT picco, giorno_picco FROM glofas_previsione
            WHERE node_lon = round($1::numeric, 4) AND node_lat = round($2::numeric, 4)
            ORDER BY corsa DESC LIMIT 1
            """,
            nodo[0],
            nodo[1],
        )
    if row is None:
        return None
    return float(row["picco"]), row["giorno_picco"]
