"""Le ore passate delle frane dal «Merging» DPC, quando è acceso (#360)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from limen.agents.executors.meteo_fetch import MeteoFetchExecutor
from limen.agents.workflows.main_workflow import _merging_per_frane
from limen.api.jobs import hourly_monitoring
from limen.config.settings import RadarArchiveSettings, Settings
from limen.core.models.context import MonitoringContext
from limen.core.models.hazard import HazardType
from limen.integrations.dpc import merging_archive
from limen.integrations.dpc.merging_archive import MergingArchive, _leggi, percorso
from limen.integrations.openmeteo.dtos import WeatherSample

_T = datetime(2026, 10, 10, 6, tzinfo=UTC)
_BBOX = (15.0, 37.95, 15.04, 38.0)


class _Client:
    """Il modello: 1 mm in ogni ora della finestra, su ogni nodo."""

    async def get_meteo_snapshot(self, **_kw: Any) -> None:
        return None

    async def get_api(self, **_kw: Any) -> None:
        return None

    async def get_rainfall_grid(
        self, *, nodes: list[Any], window_start: datetime, window_end: datetime, **_kw: Any
    ) -> list[list[WeatherSample]]:
        ore = int((window_end - window_start).total_seconds() // 3600)
        serie = [
            WeatherSample(timestamp=window_start + timedelta(hours=h), precipitation_mm=1.0)
            for h in range(1, ore + 1)
        ]
        return [list(serie) for _ in nodes]


def _tif(path: Path, valore: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=10,
        height=10,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(14.98, 38.02, 0.01, 0.01),
        nodata=-9999.0,
    ) as ds:
        ds.write(np.full((1, 10, 10), valore, dtype=np.float32))


def _executor(merging: MergingArchive | None) -> MeteoFetchExecutor:
    return MeteoFetchExecutor(
        client=_Client(),  # type: ignore[arg-type]  # finto client con la stessa forma (#360)
        window_hours=6,
        rain_node_deg=0.25,
        merging=merging,
    )


async def test_le_ore_misurate_sostituiscono_il_modello(tmp_path: Path) -> None:
    # Un blocco CUM3 da 30 mm sulle 01-03, nessun SRT1: tre ore da 10 mm.
    _tif(percorso(tmp_path, "CUM3", _T - timedelta(hours=3)), 30.0)
    ctx = MonitoringContext(aoi_id="it-prova", valuation_time=_T, bbox=_BBOX)
    out = await _executor(MergingArchive(tmp_path)).run(ctx)
    serie = out.rainfall_by_node[0]
    assert {s.timestamp.hour: s.precipitation_mm for s in serie} == {
        1: 10.0,
        2: 10.0,
        3: 10.0,
        4: 1.0,
        5: 1.0,
        6: 1.0,
    }, "le ore senza archivio restano del modello"


async def test_spento_resta_il_modello(tmp_path: Path) -> None:
    _tif(percorso(tmp_path, "CUM3", _T - timedelta(hours=3)), 30.0)
    ctx = MonitoringContext(aoi_id="it-prova", valuation_time=_T, bbox=_BBOX)
    out = await _executor(None).run(ctx)
    assert {s.precipitation_mm for s in out.rainfall_by_node[0]} == {1.0}


async def test_un_archivio_illeggibile_degrada_al_modello(tmp_path: Path) -> None:
    class _Rotto(MergingArchive):
        def oraria(self, *_a: Any, **_kw: Any) -> dict[datetime, list[float | None]]:
            raise OSError("disco")

    ctx = MonitoringContext(aoi_id="it-prova", valuation_time=_T, bbox=_BBOX)
    out = await _executor(_Rotto(tmp_path)).run(ctx)
    assert {s.precipitation_mm for s in out.rainfall_by_node[0]} == {1.0}


def test_un_file_che_arriva_dopo_non_resta_assente(tmp_path: Path) -> None:
    file = percorso(tmp_path, "CUM3", _T)
    assert _leggi(file, _T) is None
    _tif(file, 5.0)
    grid = _leggi(file, _T)
    assert grid is not None and float(grid.data.max()) == 5.0


@pytest.mark.parametrize(
    ("hazard", "cartella", "frane", "acceso"),
    [
        (HazardType.LANDSLIDE, "/x", True, True),
        (HazardType.LANDSLIDE, "/x", False, False),
        (HazardType.LANDSLIDE, "", True, False),
        (HazardType.FLOOD, "/x", True, False),
    ],
)
def test_solo_le_frane_e_solo_se_acceso(
    hazard: HazardType, cartella: str, frane: bool, acceso: bool
) -> None:
    settings = Settings(radar_archive=RadarArchiveSettings(cartella=cartella, frane=frane))
    assert (_merging_per_frane(hazard, settings) is not None) is acceso


async def test_l_aggiornamento_orario_non_ferma_lo_sweep(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _rotto(*_a: Any, **_kw: Any) -> dict[str, int]:
        raise OSError("rete")

    monkeypatch.setattr(merging_archive, "archivia", _rotto)
    await hourly_monitoring.aggiorna_merging(RadarArchiveSettings(cartella=str(tmp_path)))
