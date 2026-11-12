"""Inventario Marche-Umbria 2022 in ``landslide_events``, contro un Postgres vero (#500)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np
import pytest
from shapely import to_wkb
from shapely.geometry import Point

from limen.cli.ingest_marche_umbria import EVENTO, carica
from limen.cli.seed import run as run_seed
from limen.data.db import acquire
from tests.conftest import SEED_SMALL_AOI

pytestmark = pytest.mark.integration


def _zip(tmp_path: Path, punti: list[tuple[float, float]]) -> Path:
    import pyogrio

    cartella = tmp_path / "ELIM_DB"
    cartella.mkdir()
    for strato, scelti in (("ELIM_point", punti[:2]), ("ELIM_polygon", punti[2:])):
        geometrie = (
            [Point(x, y) for x, y in scelti]
            if strato == "ELIM_point"
            else [Point(x, y).buffer(5.0) for x, y in scelti]
        )
        pyogrio.raw.write(
            str(cartella / f"{strato}.shp"),
            np.array([to_wkb(g) for g in geometrie], dtype=object),
            [
                np.array(["Earth Slide"] * len(scelti), dtype=object),
                np.array(["Arcevia"] * len(scelti), dtype=object),
            ],
            fields=["Descriptio", "Zone"],
            geometry_type="Point" if strato == "ELIM_point" else "Polygon",
            crs="EPSG:32633",
            driver="ESRI Shapefile",
        )
    path = tmp_path / "elim.zip"
    with zipfile.ZipFile(path, "w") as archivio:
        for f in cartella.iterdir():
            archivio.write(f, f"ELIM_DB/{f.name}")
    return path


async def test_una_riga_per_cella_e_non_riscrive(
    reset_db: None, pg_pool: object, tmp_path: Path
) -> None:
    await run_seed(only=[SEED_SMALL_AOI])
    async with acquire() as conn:
        x, y = await conn.fetchrow(
            "SELECT ST_X(p), ST_Y(p) FROM (SELECT ST_Transform(centroid, 32633) AS p "
            "FROM grid_cells WHERE aoi_id = $1 ORDER BY id LIMIT 1) q",
            SEED_SMALL_AOI,
        )
    path = _zip(tmp_path, [(x, y), (x + 20.0, y), (x - 20.0, y + 10.0), (100.0, 100.0)])

    conti = await carica(path)

    assert conti is not None
    assert (conti.frane, conti.celle, conti.fuori_griglia) == (4, 1, 1)
    async with acquire() as conn:
        riga = await conn.fetchrow(
            "SELECT event_time, temporal_accuracy, geographic_accuracy, "
            "attributes->>'numero_frane' AS n FROM landslide_events "
            "WHERE source = 'marche_umbria_2022'"
        )
    assert riga["event_time"] == EVENTO
    assert (riga["temporal_accuracy"], riga["geographic_accuracy"], riga["n"]) == ("T2", "P1", "3")
    assert await carica(path) is None
