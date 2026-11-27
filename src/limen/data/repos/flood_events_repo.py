"""Catalogo datato di eventi alluvionali — il truth set del backtest (#64).

Stessa forma di :mod:`limen.data.repos.landslide_events_repo`, con una
differenza che conta: la geometria è un poligono e non un punto, perché un
allagamento *ha* un'estensione e il perimetro osservato è la cosa che rende
misurabile un backtest su celle da 1 km².

Distinto da `flood_hazard` (mosaico idraulico ISPRA), che dice dove l'acqua
*può* arrivare senza dire quando: qui ci sono allagamenti accaduti.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from shapely.geometry.base import BaseGeometry

from limen.core.logging import get_logger
from limen.data.db import acquire
from limen.integrations.copernicus_ems.client import ObservationMask, ObservedFlood

log = get_logger(__name__)


async def upsert_many(items: Iterable[ObservedFlood]) -> int:
    """Insert-or-update per id, in una transazione. Rieseguibile."""
    events = list(items)
    if not events:
        return 0
    async with acquire() as conn, conn.transaction():
        for e in events:
            await conn.execute(
                """
                INSERT INTO flood_events (
                    id, source, activation_code, aoi_label, event_time,
                    observed_time, event_type, detection_method, area_km2,
                    geom, attributes
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9,
                    ST_Multi(ST_SetSRID($10::geometry, 4326)), $11::jsonb
                )
                ON CONFLICT (id) DO UPDATE
                SET source           = EXCLUDED.source,
                    activation_code  = EXCLUDED.activation_code,
                    aoi_label        = EXCLUDED.aoi_label,
                    event_time       = EXCLUDED.event_time,
                    observed_time    = EXCLUDED.observed_time,
                    event_type       = EXCLUDED.event_type,
                    detection_method = EXCLUDED.detection_method,
                    area_km2         = EXCLUDED.area_km2,
                    geom             = EXCLUDED.geom,
                    attributes       = EXCLUDED.attributes
                """,
                e.id,
                "copernicus-ems",
                e.activation_code,
                e.aoi_label,
                e.event_time,
                e.observed_time,
                e.event_type,
                e.detection_method,
                e.area_km2,
                e.geom,
                json.dumps(e.attributes or {}, default=str),
            )
    log.info("flood_events.upsert_many", count=len(events))
    return len(events)


async def togli_superati(prodotti: Iterable[str], *, tenuti: Iterable[str]) -> int:
    """Toglie i poligoni che la fonte non ha più. Quanti ne ha tolti.

    Il rapid mapping corregge i prodotti pubblicando una versione nuova del
    layer (``_v2``, ``_v3``): con meno feature, gli id delle ultime posizioni
    non vengono più riscritti e resterebbero come allagamenti mai accaduti
    nella verità del backtest. Si guardano solo i ``prodotti`` riletti, per id
    di maschera: un poligono è ``<maschera>-<posizione>-<parte>``.
    """
    async with acquire() as conn:
        esito = await conn.execute(
            r"""
            DELETE FROM flood_events
            WHERE source = 'copernicus-ems'
              AND regexp_replace(id, '-\d+-\d+$', '') = ANY($1::text[])
              AND id <> ALL($2::text[])
            """,
            list(prodotti),
            list(tenuti),
        )
    tolti = int(esito.split()[-1])
    log.info("flood_events.superseded_removed", count=tolti)
    return tolti


async def upsert_masks(
    items: Iterable[ObservationMask], *, absent: Iterable[str] = ()
) -> tuple[int, int]:
    """Scrive le maschere di osservazione e toglie quelle ``absent``. Rieseguibile.

    ``absent`` sono maschere di prodotti che la fonte dice mai consegnati: un
    ingest precedente le scriveva per ogni prodotto con immagini, anche senza
    layer osservato, e dicevano «osservato asciutto» dove nessuno aveva
    guardato. Si tolgono nella stessa transazione delle scritte, così il
    backtest non vede mai una tabella a metà. Restituisce (scritte, tolte).
    """
    masks = list(items)
    tolte_ids = list(absent)
    if not masks and not tolte_ids:
        return 0, 0
    async with acquire() as conn, conn.transaction():
        esito = await conn.execute(
            "DELETE FROM flood_observation_masks"
            " WHERE id = ANY($1::text[]) AND source = 'copernicus-ems'",
            tolte_ids,
        )
        tolte = int(esito.split()[-1])
        for m in masks:
            await conn.execute(
                """
                INSERT INTO flood_observation_masks (
                    id, source, activation_code, aoi_label, product_type,
                    observed_time, area_km2, geom
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7,
                    ST_Multi(ST_SetSRID($8::geometry, 4326))
                )
                ON CONFLICT (id) DO UPDATE
                SET activation_code = EXCLUDED.activation_code,
                    aoi_label       = EXCLUDED.aoi_label,
                    product_type    = EXCLUDED.product_type,
                    observed_time   = EXCLUDED.observed_time,
                    area_km2        = EXCLUDED.area_km2,
                    geom            = EXCLUDED.geom
                """,
                m.id,
                "copernicus-ems",
                m.activation_code,
                m.aoi_label,
                m.product_type,
                m.observed_time,
                m.area_km2,
                m.geom,
            )
    log.info("flood_observation_masks.upsert_many", count=len(masks), removed=tolte)
    return len(masks), tolte


async def observation_times(aoi_id: str) -> dict[str, list[datetime]]:
    """``{cell_id: [istanti in cui la cella è stata osservata]}``.

    Il denominatore verificabile del FAR. Un'allerta su una cella che nessun
    passaggio satellitare ha coperto non è né vera né falsa, e infilarla fra i
    falsi è la ragione per cui il primo giro misurò FAR 100%.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT g.id AS cell_id, m.observed_time
            FROM flood_observation_masks m
            JOIN grid_cells g ON ST_Intersects(g.geom, m.geom)
            WHERE g.aoi_id = $1
            ORDER BY g.id, m.observed_time
            """,
            aoi_id,
        )
    out: dict[str, list[datetime]] = {}
    for r in rows:
        out.setdefault(str(r["cell_id"]), []).append(r["observed_time"])
    return out


async def observation_times_per_maschera(aoi_id: str) -> dict[str, list[tuple[str, datetime]]]:
    """``{cell_id: [(id maschera, istante)]}``: come :func:`observation_times`,
    con la maschera che ha guardato, per poter togliere un prodotto (#713)."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT g.id AS cell_id, m.id AS mask_id, m.observed_time
            FROM flood_observation_masks m
            JOIN grid_cells g ON ST_Intersects(g.geom, m.geom)
            WHERE g.aoi_id = $1
            ORDER BY g.id, m.observed_time
            """,
            aoi_id,
        )
    out: dict[str, list[tuple[str, datetime]]] = {}
    for r in rows:
        out.setdefault(str(r["cell_id"]), []).append((str(r["mask_id"]), r["observed_time"]))
    return out


async def truth_cells_per_prodotto(
    aoi_id: str, *, start: datetime, end: datetime
) -> dict[str, dict[str, datetime]]:
    """``{cell_id: {id maschera del prodotto: primo event_time}}``.

    :func:`truth_cells` tenendo distinto il prodotto che ha mappato l'acqua,
    così il backtest può togliere una mappa e vedere quali celle restano
    allagate per un'altra (#713). Il prodotto è il prefisso dell'id del
    poligono, ``<maschera>-<posizione>-<parte>``.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            r"""
            SELECT g.id AS cell_id,
                   regexp_replace(e.id, '-\d+-\d+$', '') AS mask_id,
                   min(e.event_time) AS first_event
            FROM flood_events e
            JOIN grid_cells g ON ST_Intersects(g.geom, e.geom)
            WHERE g.aoi_id = $1
              AND e.event_time >= $2
              AND e.event_time <= $3
            GROUP BY 1, 2
            """,
            aoi_id,
            start,
            end,
        )
    out: dict[str, dict[str, datetime]] = {}
    for r in rows:
        out.setdefault(str(r["cell_id"]), {})[str(r["mask_id"])] = r["first_event"]
    return out


async def count_events() -> int:
    async with acquire() as conn:
        row = await conn.fetchrow("SELECT count(*)::bigint AS n FROM flood_events")
    return int(row["n"]) if row else 0


async def truth_cells(aoi_id: str, *, start: datetime, end: datetime) -> dict[str, datetime]:
    """``{cell_id: primo event_time}`` per le celle intersecate da un allagamento.

    Il primo evento per cella è l'ancora: una cella allagata due volte nella
    finestra è **un** positivo, non due, altrimenti un'area ben allertata
    gonficerebbe l'hit rate quanto più spesso si allaga.

    ``ST_Intersects`` e non il centroide: i poligoni osservati sono spesso
    strisce lungo l'alveo, più stretti del chilometro della cella, e chiedere
    che coprano il centro scarterebbe la maggior parte degli allagamenti veri.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT g.id AS cell_id, min(e.event_time) AS first_event
            FROM flood_events e
            JOIN grid_cells g ON ST_Intersects(g.geom, e.geom)
            WHERE g.aoi_id = $1
              AND e.event_time >= $2
              AND e.event_time <= $3
            GROUP BY g.id
            """,
            aoi_id,
            start,
            end,
        )
    return {str(r["cell_id"]): r["first_event"] for r in rows}


async def catalogue_window() -> tuple[datetime | None, datetime | None]:
    """Copertura temporale del catalogo, per il report."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT min(event_time) AS lo, max(event_time) AS hi FROM flood_events"
        )
    if row is None:
        return None, None
    return row["lo"], row["hi"]


@dataclass(frozen=True, slots=True)
class ActivationSummary:
    """Una riga di provenienza per il report."""

    activation_code: str
    event_time: datetime
    polygons: int
    area_km2: float
    name: str | None


async def activations_summary() -> list[ActivationSummary]:
    """Una riga per attivazione: data, poligoni, area. Provenienza leggibile.

    L'area è, per AOI, quella del **prodotto più esteso**, poi sommata sulle
    AOI: ``DEL``, ``DEL_MONIT01``, ``GRA`` mostrano lo stesso posto in giorni
    diversi, e sommarli contava due o tre volte la stessa acqua (#713).
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            r"""
            WITH per_prodotto AS (
                SELECT activation_code, aoi_label,
                       COALESCE(substring(id FROM '^(.*)-[0-9]+-[0-9]+$'), aoi_label)
                           AS prodotto,
                       sum(area_km2) AS area_km2
                FROM flood_events
                GROUP BY 1, 2, 3
            ),
            per_aoi AS (
                SELECT activation_code, aoi_label, max(area_km2) AS area_km2
                FROM per_prodotto
                GROUP BY 1, 2
            ),
            per_attivazione AS (
                SELECT activation_code, sum(area_km2) AS area_km2
                FROM per_aoi
                GROUP BY 1
            )
            SELECT e.activation_code,
                   min(e.event_time) AS event_time,
                   count(*)          AS polygons,
                   min(a.area_km2)   AS area_km2,
                   min(e.attributes->>'activation_name') AS name
            FROM flood_events e
            JOIN per_attivazione a USING (activation_code)
            GROUP BY e.activation_code
            ORDER BY min(e.event_time)
            """
        )
    return [
        ActivationSummary(
            activation_code=str(r["activation_code"]),
            event_time=r["event_time"],
            polygons=int(r["polygons"]),
            area_km2=float(r["area_km2"] or 0.0),
            name=r["name"],
        )
        for r in rows
    ]


@dataclass(frozen=True, slots=True)
class PoligonoOsservato:
    """Un poligono di ``flood_events`` in EPSG:3035, per misurare aree."""

    id: str
    geom: BaseGeometry
    event_time: datetime
    observed_time: datetime | None


async def acqua_osservata(activation_code: str) -> list[PoligonoOsservato]:
    """I poligoni di un'attivazione, tutti i prodotti, in EPSG:3035.

    Quali prodotti tenere lo decide il chiamante (:func:`limen.core.ems_pai.di_monitoraggio`),
    e anche la validità: ``ST_MakeValid`` qui quintuplicava il tempo della query
    (20 s contro 4 su EMSR664), ``shapely.make_valid`` costa una frazione.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, ST_Transform(geom, 3035) AS geom,
                   event_time, observed_time
            FROM flood_events
            WHERE activation_code = $1
            ORDER BY id
            """,
            activation_code,
        )
    return [
        PoligonoOsservato(
            id=str(r["id"]),
            geom=r["geom"],
            event_time=r["event_time"],
            observed_time=r["observed_time"],
        )
        for r in rows
    ]


async def riquadro(activation_code: str) -> tuple[float, float, float, float] | None:
    """Il riquadro EPSG:4326 dell'acqua di un'attivazione, ``None`` se non c'è."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT ST_XMin(b) AS x0, ST_YMin(b) AS y0, ST_XMax(b) AS x1, ST_YMax(b) AS y1
            FROM (SELECT ST_Extent(geom)::geometry AS b
                  FROM flood_events WHERE activation_code = $1) t
            WHERE b IS NOT NULL
            """,
            activation_code,
        )
    if row is None:
        return None
    return (float(row["x0"]), float(row["y0"]), float(row["x1"]), float(row["y1"]))


@dataclass(frozen=True, slots=True)
class ComuneGeom:
    istat_code: str
    nome: str
    aoi_id: str
    geom: BaseGeometry


async def comuni_nel_riquadro(activation_code: str) -> list[ComuneGeom]:
    """I comuni ISTAT il cui riquadro tocca l'acqua dell'attivazione, in EPSG:3035.

    Solo il filtro sull'indice: l'intersezione vera la fa il chiamante, che
    ha già l'acqua in memoria. Un ``ST_Intersects`` fra ogni poligono e i
    confini comunali costava quasi due minuti su EMSR664.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            WITH r AS (
                SELECT ST_Extent(geom)::geometry AS b
                FROM flood_events WHERE activation_code = $1
            )
            SELECT c.istat_code, c.name, c.aoi_id,
                   ST_Transform(c.geom, 3035) AS geom
            FROM comuni c, r
            WHERE r.b IS NOT NULL AND c.geom && r.b
            """,
            activation_code,
        )
    return [
        ComuneGeom(
            istat_code=str(r["istat_code"]),
            nome=str(r["name"]),
            aoi_id=str(r["aoi_id"]),
            geom=r["geom"],
        )
        for r in rows
    ]


__all__ = [
    "ActivationSummary",
    "ComuneGeom",
    "PoligonoOsservato",
    "acqua_osservata",
    "activations_summary",
    "catalogue_window",
    "comuni_nel_riquadro",
    "count_events",
    "observation_times",
    "observation_times_per_maschera",
    "riquadro",
    "truth_cells",
    "truth_cells_per_prodotto",
    "upsert_many",
    "upsert_masks",
]
