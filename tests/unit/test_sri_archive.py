"""L'archivio radar IT-DPC-SRI letto dal disco, e la sua pioggia nel backtest."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from pyproj import CRS

from limen.cli.backtest import pioggia_dal_radar
from limen.integrations.dpc.sri_archive import SriArchive
from limen.integrations.openmeteo.dtos import WeatherSample

numcodecs = pytest.importorskip("numcodecs")

_TM = CRS.from_proj4("+proj=tmerc +lat_0=42 +lon_0=12.5 +k=1 +x_0=0 +y_0=0 +datum=WGS84").to_wkt()


def _archivio(tmp_path: Path, minuti: list[int], intensita: list[float]) -> Path:
    """Una griglia 4x4 da 1 km attorno all'origine (42°N 12,5°E)."""
    z = tmp_path / "sri.zarr"
    codec = numcodecs.Blosc()
    (z / "RR").mkdir(parents=True)
    (z / "crs").mkdir()
    (z / "time").mkdir()
    (z / "RR" / ".zarray").write_text(json.dumps({"shape": [len(minuti), 4, 4]}))
    (z / "crs" / ".zattrs").write_text(
        json.dumps({"GeoTransform": "-2000.0 1000.0 0.0 2000.0 0.0 -1000.0", "crs_wkt": _TM})
    )
    (z / "time" / "0").write_bytes(codec.encode(np.array(minuti, dtype="<i8").tobytes()))
    for i, v in enumerate(intensita):
        if np.isnan(v):
            continue  # fotogramma assente sul disco
        frame = np.full((4, 4), v, dtype="<f4")
        (z / "RR" / f"{i}.0.0").write_bytes(codec.encode(frame.tobytes()))
    return z


def _min(h: int, m: int = 0) -> int:
    """Minuti dal 2010-01-01 al 1° gennaio 2010 alle h:m UTC."""
    return h * 60 + m


def test_l_ora_e_la_media_delle_intensita_che_la_coprono(tmp_path: Path) -> None:
    # Fra le 00:00 e l'01:00: 6 mm/h per mezz'ora, 2 mm/h per l'altra mezza.
    minuti = [_min(0, m) for m in range(0, 60, 15)] + [_min(1)]
    z = _archivio(tmp_path, minuti, [6.0, 6.0, 2.0, 2.0, 0.0])
    ore = SriArchive(z).oraria(
        [(12.5, 42.0)], datetime(2009, 12, 31, 23, tzinfo=UTC), datetime(2010, 1, 1, 1, tzinfo=UTC)
    )
    assert ore[datetime(2010, 1, 1, 1, tzinfo=UTC)] == [pytest.approx(4.0)]


def test_un_ora_coperta_per_meno_di_meta_non_e_misurata(tmp_path: Path) -> None:
    minuti = [_min(0, m) for m in range(0, 60, 15)] + [_min(1)]
    z = _archivio(tmp_path, minuti, [5.0, np.nan, np.nan, np.nan, 0.0])
    ore = SriArchive(z).oraria(
        [(12.5, 42.0)], datetime(2009, 12, 31, 23, tzinfo=UTC), datetime(2010, 1, 1, 1, tzinfo=UTC)
    )
    assert ore[datetime(2010, 1, 1, 1, tzinfo=UTC)] == [None]


def test_un_punto_fuori_griglia_non_ha_pixel(tmp_path: Path) -> None:
    z = _archivio(tmp_path, [0], [1.0])
    assert SriArchive(z).pixel([(12.5, 42.0), (30.0, 60.0)])[1] is None


def test_il_radar_sostituisce_il_modello_solo_dove_ha_misurato() -> None:
    t1 = datetime(2019, 11, 24, 1, tzinfo=UTC)
    t2 = datetime(2019, 11, 24, 2, tzinfo=UTC)
    grezzo = [
        [
            WeatherSample(timestamp=t1, precipitation_mm=1.0, soil_moisture_0_7_cm=0.3),
            WeatherSample(timestamp=t2, precipitation_mm=2.0),
        ]
    ]
    out = pioggia_dal_radar(grezzo, {t1: [12.0], t2: [None]})
    assert [c.precipitation_mm for c in out[0]] == [12.0, 2.0]
    assert out[0][0].soil_moisture_0_7_cm == 0.3, "l'umidità del suolo resta del modello"


def test_un_punto_fuori_griglia_non_legge_il_bordo(tmp_path: Path) -> None:
    minuti = [_min(0, m) for m in range(0, 60, 15)] + [_min(1)]
    z = _archivio(tmp_path, minuti, [8.0, 8.0, 8.0, 8.0, 8.0])
    ore = SriArchive(z).oraria(
        [(12.5, 42.0), (30.0, 60.0)],
        datetime(2009, 12, 31, 23, tzinfo=UTC),
        datetime(2010, 1, 1, 1, tzinfo=UTC),
    )
    assert ore[datetime(2010, 1, 1, 1, tzinfo=UTC)] == [pytest.approx(8.0), None]
