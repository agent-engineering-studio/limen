"""Il fuoco per cella con ``firms_client.cell_stats``: la quota di coltivi sotto gli incendi (#714).

La #714 chiede un segnale oltre l'FWI per il Nord, dove l'incendio a
«moderato» prende in Lombardia un incendio su cinque: i roghi agricoli sono
la prima ipotesi. Qui, per ogni cella di una AOI, la quota media di coltivi ESA
WorldCover sotto le rilevazioni VIIRS di vegetazione dei suoi giorni-incendio,
in ``cell_static_factors.crop_burning_share``. La misura è ``limen
misura-coltivi``, che la ricalcola in memoria fino alla fine del periodo di
stima; nessun motore la legge.

La griglia è quella di Limen, passata alla libreria: ``LaeaGrid`` in
EPSG:3035 con l'origine ricavata dalle celle salvate (``<aoi>|<riga>|<colonna>``
di ``grid_repo``) e verificata su un campione. Un test di
integrazione verifica che i giorni-incendio per cella coincidano con
``fire_density``.

Solo VIIRS dal 2012: la posizione MODIS (1 km) è troppo larga per dire che
terra c'era sotto, e il raggio attorno a ogni rilevazione è mezzo pixel
VIIRS. NULL è «non misurato»: una cella senza giorni-incendio, o senza le
tile WorldCover nell'init (il passo allora si salta).
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

from firms_client import CellStats, Hotspot, LaeaGrid, cell_stats, worldcover_tiles
from firms_client.init import worldcover_path

from limen.core.logging import get_logger
from limen.data.db import acquire
from limen.data.repos.fire_events_repo import VEGETATION_FIRE, VIIRS_ERA_START
from limen.data.repos.grid_repo import DEFAULT_CELL_SIZE_M
from limen.integrations.firms.worldcover import cartella_worldcover, worldcover_locale
from limen.integrations.static_bootstrap import fingerprint

log = get_logger(__name__)

#: Celle salvate, in EPSG:3035: l'origine della griglia si ricava da loro e
#: non dal confine dell'AOI, che può essere stato ridisegnato dopo la
#: semina senza che le celle si muovessero (#333).
_CELLE_3035_SQL = """
SELECT row_idx, col_idx,
       ST_XMin(ST_Transform(geom, 3035)) AS x, ST_YMin(ST_Transform(geom, 3035)) AS y,
       ST_Y(ST_Centroid(geom)) AS lat, ST_X(ST_Centroid(geom)) AS lon
FROM grid_cells WHERE aoi_id = $1 ORDER BY id LIMIT $2
"""
#: Le celle su cui si verifica la griglia ricostruita.
_CAMPIONE = 50

_CELLE_SQL = "SELECT id FROM grid_cells WHERE aoi_id = $1"

#: Il riquadro e non il confine: le celle fuori dall'AOI si scartano dopo.
#: Lo stesso filtro fa l'impronta del passo, così una riga che il passo non
#: legge (MODIS, un'acciaieria) non lo fa ricalcolare.
_FILTRO = """
FROM fire_hotspots h
JOIN aoi a ON a.id = $1 AND h.geom && a.bbox
WHERE h.detection_type = $2 AND h.source LIKE 'VIIRS%' AND h.acq_date >= $3
  AND h.acq_date <= $4
"""
_HOTSPOT_SQL = (
    "SELECT h.latitude, h.longitude, h.acq_date, h.acq_time, h.confidence, h.frp_mw, "
    "h.brightness_k, h.daynight, h.satellite, h.instrument, h.detection_type" + _FILTRO
)
_IMPRONTA_SQL = "SELECT count(*) AS n, max(h.created_at) AS ultimo" + _FILTRO
_RIQUADRO_SQL = (
    "SELECT ST_XMin(bbox) AS o, ST_YMin(bbox) AS s, ST_XMax(bbox) AS e, ST_YMax(bbox) AS n "
    "FROM aoi WHERE id = $1"
)

#: Una passata: il valore nuovo dove c'è, NULL dove non c'è più, e solo le
#: righe che cambiano (niente ``updated_at`` riscritto su 312.000 celle).
_SCRIVI_SQL = """
UPDATE cell_static_factors c
SET crop_burning_share = n.quota, updated_at = now()
FROM grid_cells g
LEFT JOIN unnest($2::text[], $3::float8[]) AS n(id, quota) ON n.id = g.id
WHERE g.id = c.cell_id AND g.aoi_id = $1
  AND c.crop_burning_share IS DISTINCT FROM n.quota
"""

#: Come gli altri passi del bootstrap su un'AOI intera.
_TIMEOUT_S = 900.0


class GrigliaDiversaError(Exception):
    """La griglia ricostruita non mette i centri delle celle salvate nelle loro righe e colonne."""


async def griglia(aoi_id: str) -> LaeaGrid:
    """La griglia di ``aoi_id`` com'è nel database, per ``firms_client``.

    L'origine viene dalle celle salvate; su un campione si controlla che il
    centro di ogni cella cada nella sua riga e colonna, o si solleva
    :class:`GrigliaDiversaError` (una griglia di passo diverso, celle a mano).
    """
    async with acquire() as conn:
        righe = await conn.fetch(_CELLE_3035_SQL, aoi_id, _CAMPIONE)
    if not righe:
        raise ValueError(f"AOI senza celle: {aoi_id!r}")
    passo = DEFAULT_CELL_SIZE_M
    prima = righe[0]
    origine = (
        float(prima["x"]) - prima["col_idx"] * passo,
        float(prima["y"]) - prima["row_idx"] * passo,
    )
    grid = LaeaGrid(size_m=passo, origin=origine)
    for r in righe:
        if grid.cell_of(r["lat"], r["lon"]) != (r["row_idx"], r["col_idx"]):
            raise GrigliaDiversaError(f"{aoi_id}: la cella {r['row_idx']},{r['col_idx']} non torna")
    return grid


def id_cella(aoi_id: str, cella: tuple[int, int]) -> str:
    return f"{aoi_id}|{cella[0]}|{cella[1]}"


async def rilevazioni(
    aoi_id: str, *, dal: date = VIIRS_ERA_START, al: date | None = None
) -> list[Hotspot]:
    """Le rilevazioni VIIRS di vegetazione nel riquadro dell'AOI, da ``dal`` ad ``al`` (oggi)."""
    async with acquire() as conn:
        righe = await conn.fetch(_HOTSPOT_SQL, aoi_id, VEGETATION_FIRE, dal, al or date.today())
    return [
        Hotspot(
            r["latitude"],
            r["longitude"],
            r["acq_date"],
            int(r["acq_time"]),
            r["confidence"],
            r["frp_mw"],
            r["brightness_k"],
            r["daynight"],
            r["satellite"],
            r["instrument"],
            r["detection_type"],
        )
        for r in righe
    ]


async def impronta(aoi_id: str) -> fingerprint.Fingerprint:
    """Ciò che il passo legge: le rilevazioni del suo filtro e le tile WorldCover dell'AOI.

    «Sorgente mancante» se l'init non ha portato le tile.
    """
    async with acquire() as conn:
        riquadro = await conn.fetchrow(_RIQUADRO_SQL, aoi_id)
        conteggio = await conn.fetchrow(
            _IMPRONTA_SQL, aoi_id, VEGETATION_FIRE, VIIRS_ERA_START, date.today()
        )
    if riquadro is None:
        return fingerprint.missing(f"AOI assente: {aoi_id}")
    bbox = (riquadro["o"], riquadro["s"], riquadro["e"], riquadro["n"])
    cartella = cartella_worldcover()
    tile = [
        p
        for p in (worldcover_path(u, cartella.parent) for u in worldcover_tiles(bbox))
        if p.exists()
    ]
    if not tile:
        return fingerprint.missing("tile WorldCover assenti: limen worldcover-sync")
    return fingerprint.Fingerprint(
        parts=(
            f"fire_hotspots_viirs:{conteggio['n']}:{conteggio['ultimo'] or '-'}",
            *(f"{t.name}:{t.stat().st_size}" for t in tile),
        ),
        details={"rows": int(conteggio["n"]), "worldcover_tile": len(tile)},
    )


async def statistiche(
    aoi_id: str, terra: Any, *, al: date | None = None
) -> dict[str, CellStats[tuple[int, int]]]:
    """``cell_stats`` delle celle di ``aoi_id``, fuochi VIIRS fino ad ``al`` (oggi); non scrive.

    Le chiavi sono gli id di ``grid_cells``; solo le celle con fuoco, e solo
    quelle salvate.
    """
    grid = await griglia(aoi_id)
    righe = await rilevazioni(aoi_id, al=al)
    async with acquire() as conn:
        celle = {r["id"] for r in await conn.fetch(_CELLE_SQL, aoi_id)}

    def conta() -> dict[str, CellStats[tuple[int, int]]]:
        # Le tile si aprono e si chiudono nello stesso thread: GDAL tiene
        # l'ambiente per thread.
        with terra:
            stats = cell_stats(righe, grid, land=terra)
        return {id_cella(aoi_id, c): s for c, s in stats.items() if id_cella(aoi_id, c) in celle}

    out = await asyncio.to_thread(conta)
    log.info("firms.celle", aoi_id=aoi_id, rilevazioni=len(righe), celle=len(out))
    return out


async def aggiorna_quota_coltivi(aoi_id: str) -> int:
    """Riscrive ``crop_burning_share`` di ``aoi_id`` (fuochi fino a oggi); le celle misurate.

    Per misurare quanto la quota anticipa gli incendi non si usa questa
    colonna: una cella bruciata nel periodo di verifica ha la quota proprio
    per quell'incendio. ``limen misura-coltivi`` la ricalcola in memoria fino
    alla fine del periodo di stima.
    """
    terra = worldcover_locale()
    if terra is None:  # il gate del bootstrap salta prima; qui per chi la chiama da sé
        return 0
    quote = {
        k: s.cropland
        for k, s in (await statistiche(aoi_id, terra)).items()
        if s.cropland is not None
    }
    async with acquire() as conn:
        await conn.execute(
            _SCRIVI_SQL, aoi_id, list(quote), list(quote.values()), timeout=_TIMEOUT_S
        )
    log.info("firms.crop_burning_share", aoi_id=aoi_id, celle=len(quote))
    return len(quote)


__all__ = [
    "GrigliaDiversaError",
    "aggiorna_quota_coltivi",
    "griglia",
    "id_cella",
    "impronta",
    "rilevazioni",
    "statistiche",
]
