"""``limen dem-tiles`` — le tile del rilievo dal DTM, per la mappa (#318).

Legge ``LIMEN_DEM_RASTER`` (lo stesso DTM della pendenza per cella) e
scrive ``rilievo-<aoi>.pmtiles`` in ``LIMEN_DEM_TILES_DIR`` (di default
``<LIMEN_DATA_ROOT>/tiles``). Senza AOI fa l'Italia intera. Rilanciato con
la sorgente invariata non rifà niente.
"""

from __future__ import annotations

import os
from pathlib import Path

from limen.config.percorsi import radice_dati
from limen.core.logging import get_logger
from limen.integrations.dem.sync_job import DEM_RASTER_ENV
from limen.integrations.dem.terrain_tiles import genera, riquadro_aoi

log = get_logger(__name__)

#: Il DTM non ha senso sotto lo zoom 5 (l'Italia in poche tile) e oltre l'11
#: (76 m per pixel) il rilievo non cambia più la lettura: MapLibre lo
#: ingrandisce da sé.
ZOOM_MIN = 5
ZOOM_MAX = 11


def cartella_tile() -> Path:
    return Path(os.environ.get("LIMEN_DEM_TILES_DIR") or radice_dati() / "tiles")


def run(aoi_id: str | None, *, zoom_max: int = ZOOM_MAX) -> int:
    raster = os.environ.get(DEM_RASTER_ENV, "").strip()
    if not raster:
        log.error("dem_tiles.no_raster", env=DEM_RASTER_ENV)
        return 1
    attribuzione = os.environ.get("LIMEN_DEM_ATTRIBUZIONE", "").strip() or "DTM"
    nome = (aoi_id or "italia").removeprefix("it-")
    esito = genera(
        Path(raster),
        cartella_tile() / f"rilievo-{nome}.pmtiles",
        riquadro=riquadro_aoi(aoi_id),
        zoom=(ZOOM_MIN, zoom_max),
        attribuzione=attribuzione,
    )
    log.info(
        "dem_tiles.summary",
        uscita=str(esito.percorso),
        tile=esito.tile,
        mb=round(esito.byte / 1e6, 1),
        saltato=esito.saltato,
    )
    return 0
