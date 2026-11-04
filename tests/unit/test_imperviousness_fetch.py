"""Il raster CLMS del suolo sigillato, scaricato con ``imageserver-export``.

Griglia, tessere e mosaico li prova la libreria. Qui resta quello che è di
Limen: le richieste passano da ``fetch_with_retry``, il file esistente non si
riscarica, il riquadro è in 3035 a 100 m e Lampedusa ci sta dentro.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pytest
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from limen.integrations.imperviousness import fetch


def _tiff(width: int, height: int, value: int) -> bytes:
    with MemoryFile() as mem:
        with mem.open(
            driver="GTiff",
            width=width,
            height=height,
            count=1,
            dtype="uint8",
            crs="EPSG:3035",
            transform=from_origin(0, 0, 100, 100),
        ) as dst:
            dst.write(np.full((height, width), value, dtype="uint8"), 1)
        return bytes(mem.read())


async def test_le_tessere_passano_dal_retry_di_limen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chiamate: list[dict[str, Any]] = []

    async def finta(method: str, url: str, **kwargs: Any) -> httpx.Response:
        chiamate.append({"method": method, "url": url, **kwargs})
        w, h = (int(v) for v in kwargs["params"]["size"].split(","))
        return httpx.Response(200, content=_tiff(w, h, 40), headers={"content-type": "image/tiff"})

    monkeypatch.setattr(fetch, "fetch_with_retry", finta)
    dest = tmp_path / "imd.tif"
    out = await fetch.fetch_imperviousness(
        dest=dest, bounds_4326=(16.80, 41.08, 16.90, 41.14), tile_px=64
    )
    assert out == dest
    assert chiamate and all(c["url"].endswith("/exportImage") for c in chiamate)
    p = chiamate[0]["params"]
    assert (p["bboxSR"], p["imageSR"], p["interpolation"]) == (
        "3035",
        "3035",
        "RSP_NearestNeighbor",
    )
    with rasterio.open(dest) as r:
        assert r.crs.to_epsg() == 3035 and r.res == (100.0, 100.0) and r.nodata == 255
        assert (r.read(1) == 40).all()
        # La provenienza viaggia con il file: da dove, come, e per cosa.
        tags = r.tags()
        assert tags["source"].endswith("/HRL_ImperviousnessDensity_2018/ImageServer")
        assert tags["valid_range"] == "0,100" and tags["limen_layer"] == "clms_imd_2018"
    # Né il `.part` né la cartella delle tessere di `resume` sopravvivono a un giro riuscito.
    assert not list(tmp_path.glob("*.part")) and not list(tmp_path.glob("*.tiles"))


async def test_un_file_presente_non_si_riscarica(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def mai(*_a: Any, **_k: Any) -> httpx.Response:
        raise AssertionError("non doveva chiedere niente")

    monkeypatch.setattr(fetch, "fetch_with_retry", mai)
    dest = tmp_path / "imd.tif"
    dest.write_bytes(b"gia' qui")
    assert await fetch.fetch_imperviousness(dest=dest, bounds_4326=(16.8, 41.0, 16.9, 41.1)) == dest


def test_il_riquadro_italiano_contiene_lampedusa() -> None:
    """In LAEA il punto più a sud non sta in un angolo del riquadro: con i soli
    quattro angoli Lampedusa restava fuori e 28 celle siciliane senza dato."""
    from imageserver_export import Grid
    from pyproj import Transformer

    grid = Grid.from_lonlat((6.627, 35.494, 18.519, 47.092), res=fetch.RESOLUTION_M, crs=3035)
    x, y = Transformer.from_crs(4326, 3035, always_xy=True).transform(12.6288, 35.4984)
    x0, y0, x1, y1 = grid.bounds
    assert x0 <= x <= x1 and y0 <= y <= y1
    assert all(v % fetch.RESOLUTION_M == 0 for v in grid.bounds)
