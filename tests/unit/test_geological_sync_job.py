"""Sync della carta geologica: shapefile veri, database simulato (#116).

`compute_geological_stats` è già testata altrove (`test_geological_zonal.py`).
Qui si prova il pezzo attorno: leggere lo shapefile senza fidarsi del CRS né
del nome della colonna, e degradare pulito quando la sorgente manca — perché il
bootstrap statico deve proseguire anche sui deployment senza litologia.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Polygon

from limen.integrations.geological import sync_job as geo

_CELL = Polygon([(16.00, 41.00), (16.01, 41.00), (16.01, 41.01), (16.00, 41.01)])


def _litho_shapefile(
    path: Path, *, crs: str | None = "EPSG:4326", column: str = "litologia"
) -> Path:
    frame = gpd.GeoDataFrame(
        {column: ["argille", None], "codice": ["A1", "B2"]},
        geometry=[
            Polygon([(15.9, 40.9), (16.1, 40.9), (16.1, 41.1), (15.9, 41.1)]),
            Polygon([(17.0, 41.0), (17.1, 41.0), (17.1, 41.1), (17.0, 41.1)]),
        ],
        crs=crs,
    )
    out = path / "litho.shp"
    frame.to_file(out)
    return out


def test_read_polygons_skips_rows_without_a_label(tmp_path: Path) -> None:
    polys = geo._read_polygons(_litho_shapefile(tmp_path), field="litologia")
    assert [p.label for p in polys] == ["argille"]


def test_read_polygons_reprojects_to_4326(tmp_path: Path) -> None:
    """Le carte ISPRA arrivano spesso in un sistema metrico: lo shapefile va
    riportato in 4326, che è il CRS di tutte le geometrie del progetto."""
    src = gpd.read_file(_litho_shapefile(tmp_path)).to_crs("EPSG:3035")
    metric = tmp_path / "metric"
    metric.mkdir()
    src.to_file(metric / "litho.shp")
    polys = geo._read_polygons(metric / "litho.shp", field="litologia")
    minx, _miny, _maxx, _maxy = polys[0].geom.bounds
    assert 15.8 < minx < 16.0  # di nuovo gradi, non metri


def test_read_polygons_falls_back_to_the_first_text_column(tmp_path: Path) -> None:
    """Un nome di colonna diverso non deve far saltare lo strato: meglio la
    prima colonna di testo che nessuna litologia."""
    path = _litho_shapefile(tmp_path, column="descr")
    polys = geo._read_polygons(path, field="litologia")
    assert polys  # letta dalla colonna di ripiego


def test_read_faults_keeps_only_real_geometries(tmp_path: Path) -> None:
    frame = gpd.GeoDataFrame(
        {"nome": ["faglia"]},
        geometry=[LineString([(16.0, 41.0), (16.2, 41.2)])],
        crs="EPSG:4326",
    )
    frame.to_file(tmp_path / "faults.shp")
    assert len(geo._read_faults(tmp_path / "faults.shp")) == 1


async def test_sync_without_a_configured_shapefile_is_a_clean_no_op(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(geo.LITHO_SHAPEFILE_ENV, raising=False)
    assert await geo.sync_geological_for_aois(aoi_ids=["it-test"]) == 0


async def test_sync_with_a_missing_file_is_a_clean_no_op(tmp_path: Path) -> None:
    assert (
        await geo.sync_geological_for_aois(
            aoi_ids=["it-test"], lithology_shapefile=tmp_path / "non-esiste.shp"
        )
        == 0
    )


async def test_sync_with_an_unreadable_file_degrades(tmp_path: Path) -> None:
    broken = tmp_path / "rotto.shp"
    broken.write_bytes(b"non uno shapefile")
    assert await geo.sync_geological_for_aois(aoi_ids=["it-test"], lithology_shapefile=broken) == 0


async def test_sync_writes_lithology_and_fault_distance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    litho = _litho_shapefile(tmp_path)
    faults_dir = tmp_path / "f"
    faults_dir.mkdir()
    gpd.GeoDataFrame(
        {"nome": ["faglia"]},
        geometry=[LineString([(16.0, 40.99), (16.02, 40.99)])],
        crs="EPSG:4326",
    ).to_file(faults_dir / "faults.shp")

    written: list[Any] = []

    async def _cells(aoi_id: str) -> dict[str, object]:
        return {"c1": _CELL} if aoi_id == "it-test" else {}

    async def _upsert(rows: list[Any]) -> int:
        written.extend(rows)
        return len(rows)

    monkeypatch.setattr(geo, "_load_cell_geometries", _cells)
    monkeypatch.setattr(geo, "upsert_many", _upsert)

    total = await geo.sync_geological_for_aois(
        aoi_ids=["it-test", "it-vuota"],
        lithology_shapefile=litho,
        faults_shapefile=faults_dir / "faults.shp",
    )

    assert total == 1
    row = written[0]
    assert row.cell_id == "c1"
    assert row.lithology == "argille"
    assert row.dist_faults_m is not None and row.dist_faults_m >= 0


async def test_an_unreadable_faults_file_does_not_block_lithology(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le faglie sono un complemento: se il loro file è rotto la litologia
    entra comunque, senza distanza."""
    litho = _litho_shapefile(tmp_path)
    broken = tmp_path / "faglie_rotte.shp"
    broken.write_bytes(b"x")
    written: list[Any] = []

    async def _cells(_aoi_id: str) -> dict[str, object]:
        return {"c1": _CELL}

    async def _upsert(rows: list[Any]) -> int:
        written.extend(rows)
        return len(rows)

    monkeypatch.setattr(geo, "_load_cell_geometries", _cells)
    monkeypatch.setattr(geo, "upsert_many", _upsert)

    total = await geo.sync_geological_for_aois(
        aoi_ids=["it-test"], lithology_shapefile=litho, faults_shapefile=broken
    )
    assert total == 1
    assert written[0].dist_faults_m is None
