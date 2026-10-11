"""La pioggia già caduta nel ramo pluviale dell'alluvione (#199).

A Melito di Porto Salvo, la mattina del 10 ottobre 2026, la previsione a 72
ore dava 20 mm e il radar DPC ne aveva misurati 152 nelle 24 ore: il ramo
pluviale restava a zero mentre il paese si allagava.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import rasterio
from rasterio.crs import CRS

from limen.agents.executors.observed_rain import ObservedRainExecutor
from limen.core.features.assembler import assemble_bundles
from limen.core.models.context import MonitoringContext
from limen.core.models.hazard import HazardType
from limen.core.models.risk import CellFeatureBundle, DynamicInputs, StaticFactors
from limen.core.scoring.flood import FloodScoringEngine
from limen.core.scoring.regional_thresholds import FloodThresholds, load_hazard_thresholds
from limen.integrations.dpc import SriGrid

_T = dt.datetime(2026, 10, 10, 6, tzinfo=dt.UTC)


def _engine() -> FloodScoringEngine:
    t = load_hazard_thresholds(HazardType.FLOOD)
    assert isinstance(t, FloodThresholds)
    return FloodScoringEngine(t)


def _bundle(
    *, prevista: float | None, osservata: float | None, resto: float | None
) -> CellFeatureBundle:
    return CellFeatureBundle(
        aoi_id="it-calabria",
        cell_id="melito",
        static=StaticFactors(cell_id="melito", flood_hazard_norm=0.8),
        dynamic=DynamicInputs(
            valuation_time=_T,
            flood_forecast_rain_72h_mm=prevista,
            flood_rain_observed_mm=osservata,
            flood_rain_head_mm=resto,
            soil_moisture_0_7=0.35,
        ),
    )


def test_melito_il_radar_porta_la_pioggia_che_la_previsione_non_vedeva() -> None:
    senza = _engine().score(_bundle(prevista=20.0, osservata=None, resto=None))
    con = _engine().score(_bundle(prevista=20.0, osservata=152.0, resto=8.0))
    assert senza.score == 0.0
    assert con.breakdown.rain_mm == 160.0
    assert con.breakdown.rain_observed_mm == 152.0
    assert con.score >= 0.45


def test_una_osservata_minore_non_abbassa_la_previsione() -> None:
    """La previsione di un temporale in arrivo resta: vale la maggiore."""
    r = _engine().score(_bundle(prevista=110.0, osservata=5.0, resto=30.0))
    assert r.breakdown.rain_mm == 110.0


def test_senza_previsione_resta_la_pioggia_misurata() -> None:
    r = _engine().score(_bundle(prevista=None, osservata=90.0, resto=None))
    assert r.breakdown.rain_mm == 90.0
    assert r.breakdown.measured()


def test_il_radar_arriva_alla_cella_e_la_previsione_restante_al_nodo() -> None:
    ctx = MonitoringContext(
        aoi_id="aoi",
        hazard_type=HazardType.FLOOD,
        valuation_time=_T,
        cell_ids=("a", "b"),
        cell_centroids={"a": (15.0, 41.0), "b": (15.01, 41.0)},
        flood_nodes=((15.0, 41.0),),
        flood_rain_by_node=(20.0,),
        flood_rain_head_by_node=(8.0,),
        flood_river_ratio_by_node=(None,),
        flood_rain_observed_by_cell={"a": 152.0},
    )
    dyn = {b.cell_id: b.dynamic for b in assemble_bundles(ctx)}
    assert (dyn["a"].flood_rain_observed_mm, dyn["a"].flood_rain_head_mm) == (152.0, 8.0)
    assert dyn["b"].flood_rain_observed_mm is None


def _frame(observed_at: dt.datetime) -> SriGrid:
    data = np.full((10, 10), 3.0, dtype=np.float32)
    data[4:7, 4:7] = 150.0
    return SriGrid(
        data=data,
        transform=rasterio.Affine(0.1, 0, 15.0, 0, -0.1, 42.0),
        crs=CRS.from_epsg(4326),
        observed_at=observed_at,
    )


def _ctx() -> MonitoringContext:
    return MonitoringContext(
        aoi_id="aoi",
        hazard_type=HazardType.FLOOD,
        valuation_time=_T,
        cell_ids=("nubifragio", "fuori", "senza-centroide"),
        cell_centroids={"nubifragio": (15.55, 41.45), "fuori": (30.0, 50.0)},
    )


async def test_lo_step_mette_la_cumulata_sulle_celle() -> None:
    async def _fetch(hours: int) -> SriGrid:
        assert hours == 24
        return _frame(_T - dt.timedelta(minutes=20))

    out = await ObservedRainExecutor(hours=24, max_age_minutes=90, fetch=_fetch).run(_ctx())
    assert out.flood_rain_observed_by_cell == {"nubifragio": 150.0}


async def test_un_fotogramma_lontano_dall_istante_non_vale() -> None:
    """Un replay del 2024 non deve leggere la pioggia di stamattina."""

    async def _fetch(hours: int) -> SriGrid:
        return _frame(_T - dt.timedelta(hours=3))

    out = await ObservedRainExecutor(hours=24, max_age_minutes=90, fetch=_fetch).run(_ctx())
    assert out.flood_rain_observed_by_cell == {}


async def test_senza_radar_lo_sweep_prosegue() -> None:
    async def _fetch(hours: int) -> None:
        return None

    out = await ObservedRainExecutor(hours=24, max_age_minutes=90, fetch=_fetch).run(_ctx())
    assert out.flood_rain_observed_by_cell == {}
