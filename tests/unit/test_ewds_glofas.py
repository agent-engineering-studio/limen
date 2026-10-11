"""Lo storico GloFAS dall'EWDS: stessa cella e stesso riferimento di Open-Meteo (#200)."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from limen.integrations.copernicus import ewds_glofas as eg


@pytest.mark.parametrize(
    ("nodo", "cella"),
    [
        # Risposte di Open-Meteo, 11 ottobre 2026: sul bordo fra due celle va
        # a volte in su e a volte in giù, ed è l'arrotondamento in float32.
        ((11.9, 44.3), (11.875, 44.275)),
        ((12.0, 44.2), (11.975, 44.225)),
        ((16.6, 40.7), (16.625, 40.725)),
        ((7.7, 45.1), (7.675, 45.125)),
        ((15.6, 38.1), (15.625, 38.075)),
    ],
)
def test_la_cella_e_quella_di_open_meteo(
    nodo: tuple[float, float], cella: tuple[float, float]
) -> None:
    assert eg.cella_open_meteo(*nodo) == pytest.approx(cella, abs=1e-3)


def test_i_mesi_coprono_la_finestra_senza_buchi() -> None:
    m = eg.mesi(date(2024, 1, 30), date(2024, 3, 2))
    assert [(a, me) for a, me, _ in m] == [(2024, 1), (2024, 2), (2024, 3)]
    assert m[0][2] == ["30", "31"]
    assert len(m[1][2]) == 29  # bisestile
    assert m[2][2] == ["01", "02"]


def test_la_richiesta_e_glofas_4_sull_italia() -> None:
    r = eg.richiesta(2024, 5, ["16"])
    assert r["system_version"] == ["version_4_0"]
    assert r["variable"] == ["average_river_discharge_in_the_last_24_hours"]
    assert r["area"] == list(eg.AREA_ITALIA)


def _netcdf(path: Path, giorni: list[date], valori: list[list[list[float]]]) -> None:
    nc = pytest.importorskip("netCDF4")
    import numpy as np

    with nc.Dataset(path, "w") as ds:
        ds.createDimension("valid_time", len(giorni))
        ds.createDimension("latitude", 2)
        ds.createDimension("longitude", 2)
        t = ds.createVariable("valid_time", "i8", ("valid_time",))
        t.units = "seconds since 1970-01-01"
        # valid_time = fine delle 24 ore: il giorno dopo quello chiesto.
        t[:] = [int(datetime(g.year, g.month, g.day).timestamp()) + 86400 for g in giorni]
        ds.createVariable("latitude", "f8", ("latitude",))[:] = [44.325, 44.275]
        ds.createVariable("longitude", "f8", ("longitude",))[:] = [11.875, 11.925]
        v = ds.createVariable(
            "avg_dis", "f4", ("valid_time", "latitude", "longitude"), fill_value=-9999.0
        )
        v[:] = np.ma.masked_equal(np.array(valori, dtype="f4"), -9999.0)


def test_serie_legge_la_cella_giusta_e_scarta_il_mare(tmp_path: Path) -> None:
    giorni = [date(2024, 5, 10), date(2024, 5, 11), date(2024, 5, 12)]
    path = tmp_path / "m.nc"
    # [lat 44.325, lat 44.275] per [lon 11.875, lon 11.925]
    _netcdf(
        path,
        giorni,
        [
            [[1.0, 9.0], [7.0, -9999.0]],
            [[1.0, 9.0], [6.0, -9999.0]],
            [[1.0, 9.0], [8.9, -9999.0]],
        ],
    )
    faenza = (11.9, 44.3)  # → cella (11.875, 44.275)
    mare = (11.95, 44.27)  # → cella (11.925, 44.275): mascherata
    fuori = (13.0, 44.3)  # fuori dal riquadro
    serie = eg.serie_per_nodo(
        [path], [faenza, mare, fuori], inizio=date(2024, 5, 11), fine=date(2024, 5, 12)
    )
    assert serie[faenza] == pytest.approx([6.0, 8.9])
    assert serie[mare] == []
    assert serie[fuori] == []


def test_il_riferimento_vuole_un_anno_di_dati() -> None:
    lunga = [float(k) for k in range(400)]
    rif = eg.riferimenti({(1.0, 1.0): lunga, (2.0, 2.0): [5.0] * 10}, percentile=0.9)
    assert rif[(1.0, 1.0)] == pytest.approx(359.1)
    assert rif[(2.0, 2.0)] is None


def test_scarica_non_richiede_un_mese_gia_scaricato(tmp_path: Path) -> None:
    chiesti: list[str] = []

    class _Client:
        def retrieve(self, _ds: str, req: dict[str, list[str]], dest: str) -> None:
            chiesti.append(req["month"][0])
            Path(dest).write_bytes(b"x")

    eg.scarica(tmp_path, date(2024, 4, 29), date(2024, 5, 2), client=_Client())
    eg.scarica(tmp_path, date(2024, 4, 29), date(2024, 5, 2), client=_Client())
    assert chiesti == ["04", "05"]
    assert not list(tmp_path.glob("*.part"))
