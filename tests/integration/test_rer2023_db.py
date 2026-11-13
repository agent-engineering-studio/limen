"""Inventario RER2023 in ``landslide_events``, contro un Postgres vero (#500)."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import numpy as np
import pytest
from shapely import to_wkb
from shapely.geometry import Point

from limen.cli.ingest_rer2023 import EVENTO, carica
from limen.cli.seed import run as run_seed
from limen.data.db import acquire
from tests.conftest import SEED_SMALL_AOI

pytestmark = [
    pytest.mark.integration,
    # Il RAR lo apre bsdtar, che c'è nell'immagine; bsdtar apre anche lo zip
    # che il test costruisce, perché un RAR non si sa scrivere da Python.
    pytest.mark.skipif(shutil.which("bsdtar") is None, reason="serve bsdtar (libarchive-tools)"),
]


def _archivio(tmp_path: Path, punti: list[tuple[float, float]]) -> Path:
    import pyogrio

    cartella = tmp_path / "RER2023_V1"
    cartella.mkdir()
    pyogrio.raw.write(
        str(cartella / "RER2023_V1.shp"),
        np.array([to_wkb(Point(x, y).buffer(5.0)) for x, y in punti], dtype=object),
        [np.array(["DS1"] * len(punti), dtype=object)],
        fields=["ClassNew"],
        geometry_type="Polygon",
        crs="EPSG:7791",
        driver="ESRI Shapefile",
    )
    path = tmp_path / "RER2023_V1.rar"
    with zipfile.ZipFile(path, "w") as archivio:
        for f in cartella.iterdir():
            archivio.write(f, f.name)
    return path


async def test_una_riga_per_cella_con_la_data_convenzionale(
    reset_db: None, pg_pool: object, tmp_path: Path
) -> None:
    await run_seed(only=[SEED_SMALL_AOI])
    async with acquire() as conn:
        x, y = await conn.fetchrow(
            "SELECT ST_X(p), ST_Y(p) FROM (SELECT ST_Transform(centroid, 7791) AS p "
            "FROM grid_cells WHERE aoi_id = $1 ORDER BY id LIMIT 1) q",
            SEED_SMALL_AOI,
        )
    path = _archivio(tmp_path, [(x, y), (x + 20.0, y), (x - 20.0, y + 10.0), (100.0, 100.0)])

    conti = await carica(path)

    assert conti is not None
    assert (conti.frane, conti.celle, conti.fuori_griglia) == (4, 1, 1)
    async with acquire() as conn:
        riga = await conn.fetchrow(
            "SELECT event_time, temporal_accuracy, geographic_accuracy, landslide_type, "
            "attributes->>'numero_frane' AS n FROM landslide_events WHERE source = 'rer2023'"
        )
    assert riga["event_time"] == EVENTO
    assert (riga["temporal_accuracy"], riga["geographic_accuracy"]) == ("T3", "P1")
    assert (riga["landslide_type"], riga["n"]) == ("DS1", "3")
    assert await carica(path) is None
