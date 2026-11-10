"""La piena prevista in periodi di ritorno: un'etichetta dal rapporto e dal q90 (#522)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pytest

from limen.core.piena import lettura, piena


def test_il_periodo_piu_lungo_superato() -> None:
    soglie: dict[int, float | None] = {2: 150.0, 5: 300.0, 20: 600.0}
    p = piena(3.5, 100.0, soglie)
    assert p is not None and p.anni == 5 and p.picco_m3s == pytest.approx(350.0)
    sotto = piena(1.0, 100.0, soglie)
    assert sotto is not None and sotto.anni is None
    assert lettura(sotto) == "Portata prevista sotto la piena da 2 anni (soglie GloFAS)."
    oltre = piena(7.0, 100.0, soglie)
    assert oltre is not None and oltre.anni == 20


@pytest.mark.parametrize(
    ("rapporto", "q90", "soglie"),
    [
        (None, 100.0, {2: 150.0}),
        (3.0, None, {2: 150.0}),
        (3.0, 0.0, {2: 150.0}),
        (3.0, 100.0, {2: None, 5: 300.0}),
    ],
)
def test_senza_un_pezzo_non_si_dice_niente(
    rapporto: float | None, q90: float | None, soglie: dict[int, float | None]
) -> None:
    assert piena(rapporto, q90, soglie) is None


def test_la_soglia_si_legge_nella_cella_che_il_nodo_legge(tmp_path: Path) -> None:
    """Il nodo (11,0, 44,5) legge la cella GloFAS un passo a est della
    dichiarata: è lì che deve stare la soglia, non nella cella accanto."""
    nc = pytest.importorskip("netCDF4")
    from glofas_ewds.cells import open_meteo_cell

    from limen.integrations.copernicus.glofas_soglie import leggi

    lats = np.round(np.arange(45.0, 44.0, -0.05) - 0.025, 3)
    lons = np.round(np.arange(10.5, 11.5, 0.05) + 0.025, 3)
    valori = np.full((lats.size, lons.size), 1.0)
    cx, cy = open_meteo_cell(11.0, 44.5)
    r = int(np.abs(lats - cy).argmin())
    c = int(np.abs(lons - cx).argmin())
    valori[r, c] = 812.0
    # La cella accanto (mascherata) non deve contare.
    valori[r, c - 1] = np.nan
    path = tmp_path / "rl.nc"
    with nc.Dataset(path, "w") as ds:
        ds.createDimension("lat", lats.size)
        ds.createDimension("lon", lons.size)
        ds.createVariable("lat", "f8", ("lat",))[:] = lats
        ds.createVariable("lon", "f8", ("lon",))[:] = lons
        ds.createVariable("rl2", "f4", ("lat", "lon"), fill_value=-9999.0)[:] = np.where(
            np.isnan(valori), -9999.0, valori
        )
    # Il secondo nodo è fuori dal file: None, non la cella del bordo.
    assert leggi(path, [(11.0, 44.5), (0.0, 0.0)]) == [812.0, None]


def test_il_giorno_vale_solo_se_il_picco_e_quello_della_corsa() -> None:
    soglie: dict[int, float | None] = {2: 150.0, 5: 300.0, 20: 600.0}
    p = piena(3.5, 100.0, soglie, (350.5, date(2026, 11, 14)))
    assert p is not None and p.giorno == date(2026, 11, 14)
    assert lettura(p) == (
        "Portata prevista sopra la piena da 5 anni, picco previsto il 14/11 "
        "(soglie GloFAS, corsa di controllo)."
    )
    # Un picco salvato diverso è un'altra previsione: il giorno non si attacca.
    altra = piena(3.5, 100.0, soglie, (420.0, date(2026, 11, 14)))
    assert altra is not None and altra.giorno is None
    assert piena(3.5, 100.0, soglie, (350.0, None)) is not None


def test_il_giorno_del_picco_e_la_corsa_piu_l_anticipo() -> None:
    from limen.integrations.copernicus.ewds_glofas import giorno_del_picco

    corsa = date(2026, 11, 10)
    # La corsa del Serchio del 10/11: il massimo al quinto anticipo è il 14.
    serie = [2.24, 12.27, 85.1, 151.41, 187.8, 85.7, 57.21]
    assert giorno_del_picco(serie, corsa) == date(2026, 11, 14)
    assert giorno_del_picco([[1.0, float("nan"), 3.0]], corsa) == date(2026, 11, 12)
    assert giorno_del_picco([[float("nan")] * 3], corsa) is None
