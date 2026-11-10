"""``limen glofas-soglie`` sul database vero: solo i nodi nuovi, una volta (#522)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from limen.cli import glofas_soglie as cli
from limen.data.db import acquire
from limen.integrations.copernicus import glofas_soglie

pytestmark = pytest.mark.integration


def _file(path: Path, valore: float) -> Path:
    nc = pytest.importorskip("netCDF4")
    lats = np.round(np.arange(45.0, 44.0, -0.05) - 0.025, 3)
    lons = np.round(np.arange(10.5, 11.5, 0.05) + 0.025, 3)
    with nc.Dataset(path, "w") as ds:
        ds.createDimension("lat", lats.size)
        ds.createDimension("lon", lons.size)
        ds.createVariable("lat", "f8", ("lat",))[:] = lats
        ds.createVariable("lon", "f8", ("lon",))[:] = lons
        ds.createVariable("soglia", "f4", ("lat", "lon"))[:] = np.full(
            (lats.size, lons.size), valore
        )
    return path


async def test_carica_i_nodi_nuovi_e_poi_niente(
    reset_db: None, pg_pool: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = [_file(tmp_path / f"rl{a}.nc", v) for a, v in ((2, 150.0), (5, 300.0), (20, 600.0))]
    scaricati: list[Path] = []

    async def _scarica(cartella: Path) -> list[Path]:
        scaricati.append(cartella)
        return files

    monkeypatch.setattr(glofas_soglie, "scarica", _scarica)
    async with acquire() as conn:
        await conn.execute(
            "INSERT INTO glofas_riferimento (node_lon, node_lat, percentile, window_days, portata)"
            " VALUES (11.0, 44.5, 0.9, 730, 80.0) ON CONFLICT DO NOTHING"
        )
    # `glofas_riferimento` non si svuota fra i test: altri nodi possono esserci.
    assert await cli.carica() >= 1
    async with acquire() as conn:
        riga = await conn.fetchrow(
            "SELECT rl2, rl5, rl20, fonte FROM glofas_soglie"
            " WHERE node_lon = 11.0 AND node_lat = 44.5"
        )
    assert riga is not None
    assert (riga["rl2"], riga["rl5"], riga["rl20"]) == (150.0, 300.0, 600.0)
    assert riga["fonte"] == glofas_soglie.FONTE
    # Il secondo giro non ha nodi nuovi: niente download, niente scritture.
    assert await cli.carica() == 0
    assert len(scaricati) == 1
