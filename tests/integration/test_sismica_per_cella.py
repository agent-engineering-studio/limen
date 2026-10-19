"""Ogni cella riceve solo i terremoti che l'hanno scossa, con la sua PGA (#284)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx
from shapely.geometry import Polygon

from limen.agents.executors.seismic_check import SeismicCheckExecutor
from limen.core.models.context import MonitoringContext
from limen.data.db import acquire
from limen.data.object_store.filesystem import FilesystemObjectStore
from limen.data.repos.aoi_repo import upsert_aoi
from limen.data.repos.grid_repo import generate_and_store_grid
from limen.integrations._http import SharedHttpClient
from limen.integrations.ingv.shakemap_client import (
    FDSN_EVENT_URL,
    SHAKEMAP_GRID_URL_TEMPLATE,
)
from limen.integrations.ingv.sync_job import run_ingv_sync

pytestmark = pytest.mark.integration

_AOI = "aoi-sisma"
_EVENTO = "ev-sisma-001"


def _griglia() -> bytes:
    """0,01° da 16,80 a 17,00 e da 41,10 a 41,20: 10 %g a ovest di 16,89, 1 %g a est."""
    righe = []
    nlon, nlat = 21, 11
    for i in range(nlat):
        lat = 41.20 - i * 0.01
        for j in range(nlon):
            lon = 16.80 + j * 0.01
            pga = 10.0 if lon < 16.89 else 1.0
            righe.append(f"{lon:.2f} {lat:.2f} 5.0 {pga}")
    return f"""<?xml version="1.0"?>
<shakemap_grid xmlns="http://earthquake.usgs.gov/eqcenter/shakemap" event_id="{_EVENTO}">
<grid_specification lon_min="16.80" lat_min="41.10" lon_max="17.00" lat_max="41.20"
 nominal_lon_spacing="0.01" nominal_lat_spacing="0.01" nlon="{nlon}" nlat="{nlat}"/>
<grid_field index="1" name="LON" units="dd"/>
<grid_field index="2" name="LAT" units="dd"/>
<grid_field index="3" name="MMI" units="intensity"/>
<grid_field index="4" name="PGA" units="%g"/>
<grid_data>
{chr(10).join(righe)}
</grid_data>
</shakemap_grid>""".encode()


@pytest.fixture(autouse=True)
async def _reset_http() -> None:
    await SharedHttpClient.aclose()
    yield
    await SharedHttpClient.aclose()


async def test_la_scossa_arriva_solo_alle_celle_scosse(reset_db: None, tmp_path: Path) -> None:
    await upsert_aoi(
        id=_AOI,
        name="sisma",
        kind="test",
        geom=Polygon([(16.83, 41.12), (16.95, 41.12), (16.95, 41.18), (16.83, 41.18)]),
        metadata={},
    )
    await generate_and_store_grid(_AOI)
    quando = datetime.now(UTC) - timedelta(hours=3)
    feature = {
        "type": "Feature",
        "id": _EVENTO,
        "geometry": {"type": "Point", "coordinates": [16.85, 41.15, 10.0]},
        "properties": {"eventID": _EVENTO, "time": quando.isoformat(), "mag": 4.4},
    }
    with respx.mock(assert_all_called=False) as mock:
        mock.get(FDSN_EVENT_URL).mock(
            return_value=httpx.Response(
                200, json={"type": "FeatureCollection", "features": [feature]}
            )
        )
        mock.get(SHAKEMAP_GRID_URL_TEMPLATE.format(event_id=_EVENTO)).mock(
            return_value=httpx.Response(200, content=_griglia())
        )
        esito = await run_ingv_sync(
            bbox=(16.0, 40.5, 17.5, 41.8),
            object_store=FilesystemObjectStore(tmp_path),
        )
    assert esito["shakemaps"] == 1
    assert esito["celle"] > 0

    async with acquire() as conn:
        celle = await conn.fetch(
            "SELECT id, ST_X(ST_Centroid(geom)) AS lon FROM grid_cells WHERE aoi_id = $1", _AOI
        )
    ovest = {r["id"] for r in celle if r["lon"] < 16.885}
    est = {r["id"] for r in celle if r["lon"] > 16.895}
    assert ovest and est

    ctx = MonitoringContext(
        aoi_id=_AOI, valuation_time=datetime.now(UTC), cell_ids=[r["id"] for r in celle]
    )
    out = await SeismicCheckExecutor().run(ctx)
    scosse = out.seismic_per_cella
    # A ovest 0,10 g, sopra la soglia di 0,02: la cella ha il suo terremoto.
    for cella in ovest:
        (evento,) = scosse[cella]
        assert evento.event_id == _EVENTO
        assert evento.pga_g == pytest.approx(0.10)
        assert evento.distance_km < 15
    # A est 0,01 g, sotto la soglia: nessun terremoto, non quello di tutta Italia.
    assert not (est & set(scosse))


async def test_un_evento_gia_calcolato_e_vecchio_non_si_riscarica(
    reset_db: None, tmp_path: Path
) -> None:
    await upsert_aoi(
        id=_AOI,
        name="sisma",
        kind="test",
        geom=Polygon([(16.83, 41.12), (16.95, 41.12), (16.95, 41.18), (16.83, 41.18)]),
        metadata={},
    )
    await generate_and_store_grid(_AOI)
    """Dopo un giorno la ShakeMap non cambia più: non si riscaricano 10 MB ogni ora.

    Ma un evento salvato senza la PGA per cella (prima della 080) sì.
    """
    quando = datetime.now(UTC) - timedelta(days=3)
    feature = {
        "type": "Feature",
        "id": _EVENTO,
        "geometry": {"type": "Point", "coordinates": [16.85, 41.15, 10.0]},
        "properties": {"eventID": _EVENTO, "time": quando.isoformat(), "mag": 4.4},
    }
    collezione = {"type": "FeatureCollection", "features": [feature]}
    store = FilesystemObjectStore(tmp_path)

    async def giro() -> respx.Route:
        with respx.mock(assert_all_called=False) as mock:
            mock.get(FDSN_EVENT_URL).mock(return_value=httpx.Response(200, json=collezione))
            griglia = mock.get(SHAKEMAP_GRID_URL_TEMPLATE.format(event_id=_EVENTO)).mock(
                return_value=httpx.Response(200, content=_griglia())
            )
            await run_ingv_sync(bbox=(16.0, 40.5, 17.5, 41.8), object_store=store)
        return griglia

    assert (await giro()).call_count == 1
    assert (await giro()).call_count == 0
    async with acquire() as conn:
        await conn.execute("UPDATE seismic_events SET pga_celle_at = NULL")
    assert (await giro()).call_count == 1
    assert (await giro()).call_count == 0
    # Codex, #288: una regione aggiunta dopo il calcolo rimette in gioco l'evento.
    async with acquire() as conn:
        await conn.execute("UPDATE grid_cells SET created_at = now() + interval '1 minute'")
    assert (await giro()).call_count == 1
