"""La griglia ShakeMap INGV letta per punto (#284), nel formato verificato dal vivo."""

from __future__ import annotations

import pytest

from limen.integrations.ingv.shakemap_grid import GrigliaNonValidaError, leggi_griglia


def griglia_xml(righe: list[str], *, nlon: int = 3, nlat: int = 2) -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<shakemap_grid xmlns="http://earthquake.usgs.gov/eqcenter/shakemap" event_id="x">
<event event_id="x" magnitude="4.0" lat="43.69" lon="10.36"/>
<grid_specification lon_min="10.0" lat_min="43.0" lon_max="10.2" lat_max="43.1"
 nominal_lon_spacing="0.1" nominal_lat_spacing="0.1" nlon="{nlon}" nlat="{nlat}"/>
<grid_field index="1" name="LON" units="dd"/>
<grid_field index="2" name="LAT" units="dd"/>
<grid_field index="3" name="MMI" units="intensity"/>
<grid_field index="4" name="PGA" units="%g"/>
<grid_data>
{chr(10).join(righe)}
</grid_data>
</shakemap_grid>""".encode()


RIGHE = [
    # Dal bordo nord, longitudine più veloce; PGA in percento di g.
    "10.0 43.1 4.0 5.0",
    "10.1 43.1 4.0 7.5",
    "10.2 43.1 4.0 1.0",
    "10.0 43.0 4.0 2.0",
    "10.1 43.0 4.0 3.0",
    "10.2 43.0 4.0 0.5",
]


def test_la_pga_e_in_g_e_si_legge_dal_punto_piu_vicino() -> None:
    g = leggi_griglia(griglia_xml(RIGHE))
    assert g.pga_in(10.1, 43.1) == pytest.approx(0.075)
    assert g.pga_in(10.04, 43.02) == pytest.approx(0.02)
    assert g.pga_in(10.2, 43.0) == pytest.approx(0.005)
    assert g.riquadro == pytest.approx((10.0, 43.0, 10.2, 43.1))


def test_fuori_dalla_griglia_non_c_e_valore() -> None:
    g = leggi_griglia(griglia_xml(RIGHE))
    assert g.pga_in(9.5, 43.05) is None
    assert g.pga_in(10.1, 44.0) is None


@pytest.mark.parametrize(
    "xml",
    [
        b"<non xml",
        griglia_xml(RIGHE[:4]),  # righe che non tornano con nlon x nlat
        griglia_xml(RIGHE).replace(b'name="PGA"', b'name="PGV"'),
    ],
)
def test_una_griglia_illeggibile_si_dice(xml: bytes) -> None:
    with pytest.raises(GrigliaNonValidaError):
        leggi_griglia(xml)
