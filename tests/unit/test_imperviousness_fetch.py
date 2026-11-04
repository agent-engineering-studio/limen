"""Scaricamento del raster CLMS del suolo sigillato.

La meccanica (griglia, tessere, mosaico atomico) è di ``imageserver-export`` e
si prova lì. Qui si prova ciò che Limen sceglie: la griglia a 100 m in
EPSG:3035 che contiene le AOI, il sentinella 255 che non conta come dato, e
il contratto "un file o nessuno" visto da chi chiama, senza rete.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pytest
import rasterio
from imageserver_export import ImageServerError
from pyproj import Transformer
from rasterio.transform import from_origin

from limen.integrations.imperviousness.fetch import (
    CLMS_IMD_2018_URL,
    NODATA,
    RESOLUTION_M,
    fetch_imperviousness,
    grid_for,
)

_BOX = (16.6, 40.9, 17.2, 41.3)


def test_grid_grows_outward_to_whole_pixels() -> None:
    grid = grid_for(_BOX)
    assert grid.crs == 3035 and grid.res == RESOLUTION_M
    x0, y0, x1, y1 = grid.bounds
    assert all(v % RESOLUTION_M == 0.0 for v in grid.bounds)
    # Il riquadro deve *contenere* l'originale, non approssimarlo: arrotondare
    # verso l'interno taglierebbe le celle sul bordo dell'AOI.
    t = Transformer.from_crs(4326, 3035, always_xy=True)
    for lon in (16.6, 17.2):
        for lat in (40.9, 41.3):
            x, y = t.transform(lon, lat)
            assert x0 <= x <= x1
            assert y0 <= y <= y1


def test_grid_covers_the_curved_south_edge() -> None:
    """In LAEA il punto più a sud non sta in un angolo del riquadro.

    Prendendo solo i quattro angoli il bordo meridionale rientrava di 6,8 km:
    abbastanza da lasciare Lampedusa fuori dal raster e 28 celle siciliane
    senza dato.
    """
    x0, y0, x1, y1 = grid_for((6.627, 35.494, 18.519, 47.092)).bounds
    t = Transformer.from_crs(4326, 3035, always_xy=True)
    x, y = t.transform(12.6288, 35.4984)  # Lampedusa, il punto più a sud d'Italia
    assert x0 <= x <= x1
    assert y0 <= y <= y1


def test_the_manifest_url_is_the_export_operation() -> None:
    assert CLMS_IMD_2018_URL.endswith("/HRL_ImperviousnessDensity_2018/ImageServer/exportImage")


def _tiff(width: int, height: int, value: int) -> bytes:
    buf = io.BytesIO()
    with rasterio.open(
        buf,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=1,
        dtype="uint8",
        crs="EPSG:3035",
        transform=from_origin(0.0, 0.0, RESOLUTION_M, RESOLUTION_M),
    ) as dst:
        dst.write(np.full((height, width), value, dtype="uint8"), 1)
    return buf.getvalue()


class _Service:
    """Un ImageServer finto: metà delle tessere sigillate al 40 %, metà mare."""

    def __init__(self, *, error: bool = False) -> None:
        self.error = error
        self.params: list[dict[str, str]] = []

    async def __call__(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        assert method == "GET" and url.endswith("/exportImage")
        params = kwargs["params"]
        self.params.append(params)
        if self.error:
            return httpx.Response(
                200,
                json={"error": {"code": 400, "message": "Invalid bbox"}},
                headers={"content-type": "application/json"},
            )
        w, h = (int(v) for v in params["size"].split(","))
        value = 40 if len(self.params) % 2 else NODATA
        return httpx.Response(
            200, content=_tiff(w, h, value), headers={"content-type": "image/tiff"}
        )


async def test_fetch_writes_the_mosaic_in_3035_with_nearest_neighbour(tmp_path: Path) -> None:
    service = _Service()
    dest = tmp_path / "imd.tif"
    path = await fetch_imperviousness(dest=dest, bounds_4326=_BOX, tile_px=256, send=service)
    assert path == dest and dest.exists()
    assert not dest.with_name("imd.tif.part").exists()
    assert all(p["interpolation"] == "RSP_NearestNeighbor" for p in service.params)
    assert all(p["bboxSR"] == "3035" and p["imageSR"] == "3035" for p in service.params)
    grid = grid_for(_BOX)
    with rasterio.open(dest) as r:
        band = r.read(1)
        assert r.crs.to_epsg() == 3035 and r.res == (RESOLUTION_M, RESOLUTION_M)
        assert (r.width, r.height) == (grid.width, grid.height)
        assert r.nodata == NODATA
    assert set(np.unique(band)) == {40, NODATA}


async def test_fetch_does_nothing_when_the_file_exists(tmp_path: Path) -> None:
    dest = tmp_path / "imd.tif"
    dest.write_bytes(b"gia scaricato")
    service = _Service()
    assert await fetch_imperviousness(dest=dest, bounds_4326=_BOX, send=service) == dest
    assert service.params == []


async def test_a_json_error_with_http_200_leaves_no_file(tmp_path: Path) -> None:
    """Il servizio risponde all'errore con 200 e un JSON: niente raster bugiardo."""
    dest = tmp_path / "imd.tif"
    with pytest.raises(ImageServerError, match="Invalid bbox"):
        await fetch_imperviousness(
            dest=dest, bounds_4326=_BOX, tile_px=256, send=_Service(error=True)
        )
    assert not dest.exists() and not dest.with_name("imd.tif.part").exists()
