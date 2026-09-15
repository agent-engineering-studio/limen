"""Job raster del bootstrap statico: DTM, CORINE e suolo impermeabilizzato (#116).

GeoTIFF veri scritti al volo, database simulato. Le proprietà da provare sono
quelle che cambiano il punteggio senza dirlo:

* una cella che il mosaico **non copre** resta assente, non zero — scrivere 0
  direbbe "interamente permeabile" e spegnerebbe l'amplificazione urbana
  proprio dove il dato manca;
* un valore fuori dall'intervallo del prodotto è "sconosciuto", non un dato;
* sorgente non configurata o file assente sono no-op puliti, perché il
  bootstrap deve proseguire sui deployment che non hanno quel layer.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Polygon

from limen.integrations.corine import sync_job as corine_sync
from limen.integrations.corine import zonal as corine_zonal
from limen.integrations.dem import sync_job as dem
from limen.integrations.imperviousness import sync_job as imperv

#: 10x10 pixel da 0,001° con origine in alto a sinistra a (16.00, 41.01):
#: copre il quadrato 16.00-16.01 E, 41.00-41.01 N.
_ORIGIN = (16.00, 41.01)
_PIX = 0.001

_INSIDE = Polygon([(16.001, 41.001), (16.009, 41.001), (16.009, 41.009), (16.001, 41.009)])
_OUTSIDE = Polygon([(17.0, 42.0), (17.01, 42.0), (17.01, 42.01), (17.0, 42.01)])


def _geotiff(path: Path, band: np.ndarray, *, nodata: float | None = None) -> Path:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=band.shape[1],
        height=band.shape[0],
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(_ORIGIN[0], _ORIGIN[1], _PIX, _PIX),
        nodata=nodata,
    ) as dst:
        dst.write(band.astype("float32"), 1)
    return path


# ---------------------------------------------------------------------------
# Suolo impermeabilizzato
# ---------------------------------------------------------------------------
def test_cell_means_normalise_to_a_fraction(tmp_path: Path) -> None:
    raster = _geotiff(tmp_path / "imd.tif", np.full((10, 10), 50.0))
    means = imperv.cell_means(raster_path=raster, cells={"dentro": _INSIDE})
    assert means == {"dentro": pytest.approx(0.5)}


def test_a_cell_outside_the_mosaic_is_absent_not_zero(tmp_path: Path) -> None:
    raster = _geotiff(tmp_path / "imd.tif", np.full((10, 10), 80.0))
    means = imperv.cell_means(raster_path=raster, cells={"fuori": _OUTSIDE, "dentro": _INSIDE})
    assert "fuori" not in means
    assert "dentro" in means


def test_values_outside_the_product_range_are_unknown(tmp_path: Path) -> None:
    """255 è il "nessun dato" di molti mosaici CLMS senza tag nodata: letto come
    valore, gonfierebbe la media oltre il 100 %."""
    band = np.full((10, 10), 255.0)
    band[:, :5] = 20.0
    raster = _geotiff(tmp_path / "imd.tif", band)
    means = imperv.cell_means(raster_path=raster, cells={"dentro": _INSIDE})
    assert means["dentro"] == pytest.approx(0.2)


def test_a_cell_with_only_invalid_pixels_is_absent(tmp_path: Path) -> None:
    raster = _geotiff(tmp_path / "imd.tif", np.full((10, 10), 255.0))
    assert imperv.cell_means(raster_path=raster, cells={"dentro": _INSIDE}) == {}


def test_cell_means_on_a_missing_raster_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        imperv.cell_means(raster_path=tmp_path / "manca.tif", cells={})


class _Conn:
    def __init__(self, cells: dict[str, Any]) -> None:
        self._cells = cells
        self.updates: list[tuple[str, float]] = []

    async def fetch(self, _sql: str, aoi_id: str) -> list[dict[str, Any]]:
        return [{"id": k, "geom": v} for k, v in self._cells.items()] if aoi_id == "it-x" else []

    async def executemany(self, _sql: str, rows: list[tuple[str, float]]) -> None:
        self.updates.extend(rows)


def _use(monkeypatch: pytest.MonkeyPatch, module: Any, conn: _Conn) -> None:
    @asynccontextmanager
    async def _acquire():
        yield conn

    monkeypatch.setattr(module, "acquire", _acquire)


async def test_sync_imperviousness_writes_covered_cells(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raster = _geotiff(tmp_path / "imd.tif", np.full((10, 10), 40.0))
    conn = _Conn({"dentro": _INSIDE, "fuori": _OUTSIDE})
    _use(monkeypatch, imperv, conn)

    written = await imperv.sync_imperviousness_for_aois(
        aoi_ids=["it-x", "it-vuota"], raster_path=raster
    )
    assert written == 1
    assert conn.updates == [("dentro", pytest.approx(0.4))]


async def test_sync_imperviousness_with_no_coverage_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raster = _geotiff(tmp_path / "imd.tif", np.full((10, 10), 40.0))
    conn = _Conn({"fuori": _OUTSIDE})
    _use(monkeypatch, imperv, conn)
    assert await imperv.sync_imperviousness_for_aois(aoi_ids=["it-x"], raster_path=raster) == 0
    assert conn.updates == []


async def test_sync_imperviousness_without_a_source_is_a_no_op(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(imperv.IMPERVIOUSNESS_RASTER_ENV, raising=False)
    assert await imperv.sync_imperviousness_for_aois(aoi_ids=["it-x"]) == 0
    assert (
        await imperv.sync_imperviousness_for_aois(aoi_ids=["it-x"], raster_path=tmp_path / "x.tif")
        == 0
    )


def test_imperviousness_path_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(imperv.IMPERVIOUSNESS_RASTER_ENV, "/dati/imd.tif")
    assert imperv._resolve_raster_path(None) == Path("/dati/imd.tif")


# ---------------------------------------------------------------------------
# DTM
# ---------------------------------------------------------------------------
async def test_sync_dem_without_a_source_is_a_no_op(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(dem.DEM_RASTER_ENV, raising=False)
    assert await dem.sync_dem_for_aois(aoi_ids=["it-x"]) == 0
    assert await dem.sync_dem_for_aois(aoi_ids=["it-x"], raster_path=tmp_path / "x.tif") == 0


async def test_sync_dem_writes_cells_with_pixels_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Una cella senza pixel non entra: il DTM non la copre, e scriverle una
    pendenza nulla la farebbe sembrare pianura."""
    raster = _geotiff(tmp_path / "dtm.tif", np.tile(np.arange(10, dtype=float) * 5, (10, 1)))
    written: list[Any] = []

    async def _cells(aoi_id: str) -> dict[str, Any]:
        return {"dentro": _INSIDE, "fuori": _OUTSIDE} if aoi_id == "it-x" else {}

    async def _upsert(rows: list[Any]) -> int:
        written.extend(rows)
        return len(rows)

    monkeypatch.setattr(dem, "_load_cell_geometries", _cells)
    monkeypatch.setattr(dem, "upsert_many", _upsert)

    total = await dem.sync_dem_for_aois(aoi_ids=["it-x", "it-vuota"], raster_path=raster)

    assert total == 1
    assert [r.cell_id for r in written] == ["dentro"]
    assert written[0].elevation_m is not None


async def test_sync_dem_on_an_uncovered_aoi_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raster = _geotiff(tmp_path / "dtm.tif", np.full((10, 10), 100.0))

    async def _cells(_aoi_id: str) -> dict[str, Any]:
        return {"fuori": _OUTSIDE}

    async def _upsert(rows: list[Any]) -> int:
        raise AssertionError("nessuna riga doveva essere scritta")

    monkeypatch.setattr(dem, "_load_cell_geometries", _cells)
    monkeypatch.setattr(dem, "upsert_many", _upsert)
    assert await dem.sync_dem_for_aois(aoi_ids=["it-x"], raster_path=raster) == 0


# ---------------------------------------------------------------------------
# CORINE
# ---------------------------------------------------------------------------
def _corine(path: Path, band: np.ndarray, *, nodata: int | None = 0) -> Path:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=band.shape[1],
        height=band.shape[0],
        count=1,
        dtype="uint16",
        crs="EPSG:4326",
        transform=from_origin(_ORIGIN[0], _ORIGIN[1], _PIX, _PIX),
        nodata=nodata,
    ) as dst:
        dst.write(band.astype("uint16"), 1)
    return path


def test_landuse_is_the_majority_class_inside_the_cell(tmp_path: Path) -> None:
    """Tre quarti di bosco di conifere (312), un quarto di urbano (111): la
    cella è bosco. Il nodata non vota."""
    band = np.full((10, 10), 312)
    band[:, 7:] = 111
    band[0, :] = 0
    raster = _corine(tmp_path / "clc.tif", band)

    (dentro, fuori) = corine_zonal.compute_landuse_stats(
        raster_path=raster, cells={"dentro": _INSIDE, "fuori": _OUTSIDE}
    )

    assert dentro.landuse_code == "312"
    assert dentro.pixel_count > 0
    assert fuori.landuse_code is None and fuori.pixel_count == 0


def test_landuse_on_a_missing_raster_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        corine_zonal.compute_landuse_stats(raster_path=tmp_path / "manca.tif", cells={})


async def test_sync_corine_writes_only_classified_cells(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raster = _corine(tmp_path / "clc.tif", np.full((10, 10), 211))
    written: list[Any] = []

    async def _cells(aoi_id: str) -> dict[str, Any]:
        return {"dentro": _INSIDE, "fuori": _OUTSIDE} if aoi_id == "it-x" else {}

    async def _upsert(rows: list[Any]) -> int:
        written.extend(rows)
        return len(rows)

    monkeypatch.setattr(corine_sync, "_load_cell_geometries", _cells)
    monkeypatch.setattr(corine_sync, "upsert_many", _upsert)

    assert (
        await corine_sync.sync_corine_for_aois(aoi_ids=["it-x", "it-vuota"], raster_path=raster)
        == 1
    )
    assert [(r.cell_id, r.landuse_code) for r in written] == [("dentro", "211")]


async def test_sync_corine_without_a_source_is_a_no_op(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(corine_sync.CORINE_RASTER_ENV, raising=False)
    assert await corine_sync.sync_corine_for_aois(aoi_ids=["it-x"]) == 0
    assert (
        await corine_sync.sync_corine_for_aois(aoi_ids=["it-x"], raster_path=tmp_path / "x.tif")
        == 0
    )
    monkeypatch.setenv(corine_sync.CORINE_RASTER_ENV, "/dati/clc.tif")
    assert corine_sync._resolve_raster_path(None) == Path("/dati/clc.tif")


async def test_cell_geometries_skip_rows_without_a_geometry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le tre funzioni di lettura delle celle sono gemelle: una cella senza
    geometria non entra in nessuno dei tre zonali."""

    class _Rows:
        async def fetch(self, _sql: str, _aoi: str) -> list[dict[str, Any]]:
            return [{"id": "c1", "geom": _INSIDE}, {"id": "c2", "geom": None}]

    for module in (corine_sync, dem, imperv):
        _use(monkeypatch, module, _Rows())
    assert list((await corine_sync._load_cell_geometries("it-x")).keys()) == ["c1"]
    assert list((await dem._load_cell_geometries("it-x")).keys()) == ["c1"]
    assert "c1" in await imperv._cell_geometries("it-x")
