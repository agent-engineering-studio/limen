"""Catasti regionali degli incendi nel DB e nel backtest, contro un Postgres vero (#498)."""

from __future__ import annotations

import zipfile
from datetime import date
from pathlib import Path

import numpy as np
import pytest
from shapely import to_wkb
from shapely.geometry import Point

from limen.cli import catasti_incendi
from limen.cli.backtest_wildfire import Verita, fetch_burnt_cells
from limen.cli.seed import run as run_seed
from limen.data.db import acquire
from tests.conftest import SEED_SMALL_AOI

pytestmark = pytest.mark.integration


def _zip(tmp_path: Path, x: float, y: float) -> Path:
    import pyogrio

    # Due poligoni dello stesso incendio (come l'Emilia-Romagna per uso del
    # suolo) e uno d'un altro incendio, piccolo, un anno dopo.
    geometrie = [Point(x, y).buffer(200), Point(x + 300, y).buffer(200), Point(x, y).buffer(20)]
    shp = tmp_path / "incendi.shp"
    pyogrio.raw.write(
        str(shp),
        np.array([to_wkb(g) for g in geometrie]),
        [
            np.array(["7", "7", "9"], dtype=object),
            np.array(["28/08/2023", "29/08/2023", "02/07/2024"], dtype=object),
        ],
        fields=["INC_ID", "DATA_INC"],
        geometry_type="Polygon",
        crs="EPSG:25833",
        driver="ESRI Shapefile",
    )
    path = tmp_path / "catasto.zip"
    with zipfile.ZipFile(path, "w") as archivio:
        for f in tmp_path.glob("incendi.*"):
            archivio.write(f, f.name)
    return path


async def test_un_incendio_per_chiave_e_verita_separata_da_effis(
    reset_db: None, pg_pool: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await run_seed(only=[SEED_SMALL_AOI])
    async with acquire() as conn:
        cella, x, y = await conn.fetchrow(
            "SELECT id, ST_X(p), ST_Y(p) FROM (SELECT id, ST_Transform(centroid, 25833) AS p "
            "FROM grid_cells WHERE aoi_id = $1 ORDER BY id LIMIT 1) q",
            SEED_SMALL_AOI,
        )
    path = _zip(tmp_path, x, y)

    async def scarica(_ente: object, _oggi: date) -> list[Path]:
        return [path]

    monkeypatch.setattr(catasti_incendi, "scarica", scarica)
    ente = catasti_incendi.ENTI[0]

    conti = await catasti_incendi.carica(ente, forzato=False, oggi=date(2026, 11, 12))

    assert conti == {"poligoni": 3, "senza_data": 0, "incendi": 2}
    async with acquire() as conn:
        righe = await conn.fetch(
            "SELECT id, fire_date, area_ha FROM catasti_incendi ORDER BY fire_date"
        )
        effis = await conn.fetchval("SELECT count(*) FROM fire_perimeters")
    assert [(r["id"], r["fire_date"]) for r in righe] == [
        (f"{ente.fonte}:7", date(2023, 8, 28)),
        (f"{ente.fonte}:9", date(2024, 7, 2)),
    ]
    # Due dischi da 200 m a 300 m di distanza: 25,1 ha meno 1,8 di sovrapposizione.
    assert righe[0]["area_ha"] == pytest.approx(23.3, rel=0.03)
    assert effis == 0

    finestra = {"start": date(2023, 1, 1), "end": date(2024, 12, 31)}
    assert await fetch_burnt_cells(SEED_SMALL_AOI, **finestra) == {}
    catasti = await fetch_burnt_cells(SEED_SMALL_AOI, **finestra, verita=Verita(fonte="catasti"))
    assert catasti[cella][0] == date(2023, 8, 28)
    piccoli = await fetch_burnt_cells(
        SEED_SMALL_AOI, **finestra, verita=Verita(fonte="tutte", ettari_max=1.0)
    )
    assert piccoli[cella][0] == date(2024, 7, 2)

    assert await catasti_incendi.carica(ente, forzato=False, oggi=date(2026, 11, 12)) is None
