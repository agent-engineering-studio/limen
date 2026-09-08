"""Pianificazione e mosaicatura del raster CLMS del suolo sigillato.

Le proprietà che contano sono geometriche, quindi si provano senza rete: le
tessere devono partizionare esattamente il raster (un pixel scritto due volte
o zero volte è un buco o una sovrascrittura), i loro bbox devono ricadere
esattamente sui confini di pixel, e una risposta di dimensione diversa da
quella chiesta deve fermare tutto invece di essere incollata spostata.
"""

from __future__ import annotations

import io

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from limen.integrations.imperviousness.fetch import (
    NODATA,
    RESOLUTION_M,
    Tile,
    _paste,
    plan_tiles,
    snap_bounds,
)


def test_tiles_partition_the_raster_exactly() -> None:
    width, height = 542, 488
    tiles = plan_tiles(width, height, tile_px=256)
    coverage = np.zeros((height, width), dtype=np.uint8)
    for t in tiles:
        coverage[t.row_off : t.row_off + t.height, t.col_off : t.col_off + t.width] += 1
    # Ogni pixel esattamente una volta: nessun buco, nessuna sovrapposizione.
    assert coverage.min() == 1
    assert coverage.max() == 1


def test_edge_tiles_are_clamped_not_overhanging() -> None:
    tiles = plan_tiles(300, 100, tile_px=256)
    assert [(t.width, t.height) for t in tiles] == [(256, 100), (44, 100)]


def test_tile_bounds_land_on_pixel_edges() -> None:
    tile = Tile(col_off=256, row_off=512, width=100, height=50)
    x0, y0, x1, y1 = tile.bounds(origin_x=4_000_000.0, origin_y=2_500_000.0, res=100.0)
    assert (x0, y1) == (4_025_600.0, 2_448_800.0)
    assert x1 - x0 == 100 * 100.0
    assert y1 - y0 == 50 * 100.0
    # Multipli esatti della risoluzione: è ciò che impedisce al servizio di
    # ricampionare per far combaciare la dimensione richiesta.
    assert all(v % 100.0 == 0.0 for v in (x0, y0, x1, y1))


def test_snap_bounds_grows_outward_to_the_grid() -> None:
    box = snap_bounds((16.6, 40.9, 17.2, 41.3))
    assert all(v % RESOLUTION_M == 0.0 for v in box)
    x0, y0, x1, y1 = box
    assert x1 > x0 and y1 > y0
    # Il riquadro deve *contenere* l'originale, non approssimarlo: arrotondare
    # verso l'interno taglierebbe le celle sul bordo dell'AOI.
    from pyproj import Transformer

    t = Transformer.from_crs(4326, 3035, always_xy=True)
    for lon in (16.6, 17.2):
        for lat in (40.9, 41.3):
            x, y = t.transform(lon, lat)
            assert x0 <= x <= x1
            assert y0 <= y <= y1


def _tiff_bytes(width: int, height: int, value: int) -> bytes:
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


def test_paste_writes_into_the_window_and_counts_valid_pixels(tmp_path: object) -> None:
    from pathlib import Path

    out = Path(str(tmp_path)) / "m.tif"
    with rasterio.open(
        out,
        "w",
        driver="GTiff",
        width=8,
        height=8,
        count=1,
        dtype="uint8",
        crs="EPSG:3035",
        transform=from_origin(0.0, 0.0, RESOLUTION_M, RESOLUTION_M),
        nodata=NODATA,
    ) as dst:
        tile = Tile(col_off=4, row_off=0, width=4, height=4)
        valid = _paste(dst, _tiff_bytes(4, 4, 42), tile)
    assert valid == 16

    with rasterio.open(out) as src:
        band = src.read(1)
    assert (band[0:4, 4:8] == 42).all()


def test_paste_does_not_count_the_nodata_sentinel(tmp_path: object) -> None:
    from pathlib import Path

    out = Path(str(tmp_path)) / "m.tif"
    with rasterio.open(
        out,
        "w",
        driver="GTiff",
        width=4,
        height=4,
        count=1,
        dtype="uint8",
        crs="EPSG:3035",
        transform=from_origin(0.0, 0.0, RESOLUTION_M, RESOLUTION_M),
        nodata=NODATA,
    ) as dst:
        valid = _paste(dst, _tiff_bytes(4, 4, NODATA), Tile(0, 0, 4, 4))
    # 255 è "non so", non "0 % sigillato": non entra nel conteggio dei validi.
    assert valid == 0


def test_paste_refuses_a_tile_of_the_wrong_size(tmp_path: object) -> None:
    """Incollarla comunque sposterebbe i dati di qualche pixel, in silenzio."""
    from pathlib import Path

    out = Path(str(tmp_path)) / "m.tif"
    with (
        rasterio.open(
            out,
            "w",
            driver="GTiff",
            width=8,
            height=8,
            count=1,
            dtype="uint8",
            crs="EPSG:3035",
            transform=from_origin(0.0, 0.0, RESOLUTION_M, RESOLUTION_M),
            nodata=NODATA,
        ) as dst,
        pytest.raises(RuntimeError, match="non combacia"),
    ):
        _paste(dst, _tiff_bytes(3, 4, 10), Tile(0, 0, 4, 4))


def test_snap_bounds_covers_the_curved_south_edge() -> None:
    """In LAEA il punto più a sud non sta in un angolo del riquadro.

    Prendendo solo i quattro angoli il bordo meridionale rientrava di 6,8 km:
    abbastanza da lasciare Lampedusa fuori dal raster e 28 celle siciliane
    senza dato.
    """
    from pyproj import Transformer

    box = snap_bounds((6.627, 35.494, 18.519, 47.092))
    t = Transformer.from_crs(4326, 3035, always_xy=True)
    x, y = t.transform(12.6288, 35.4984)  # Lampedusa, il punto più a sud d'Italia
    assert box[0] <= x <= box[2]
    assert box[1] <= y <= box[3]
