"""Build one :class:`CellFeatureBundle` per cell from a workflow context.

Pure function: takes the snapshots already collected in
:class:`MonitoringContext` and shapes them into the engine's input
DTOs. No I/O. The executor layer is responsible for filling the
context; this is the deterministic glue.

The same assembler will feed the V2 ML engine (`Limen_Project_Document.md`
§3.15), which is why the function is decoupled from any concrete
scorer.
"""

from __future__ import annotations

from collections.abc import Sequence

from limen.core.models.context import MonitoringContext
from limen.core.models.risk import (
    CellFeatureBundle,
    DynamicInputs,
    RainfallSample,
    RainfallSeries,
    SeismicHistoryEvent,
    StaticFactors,
)


def _rainfall_series(ctx: MonitoringContext) -> RainfallSeries:
    """Coerce the (Open-Meteo-derived) samples list into a typed series."""
    samples: list[RainfallSample] = []
    for s in ctx.meteo_samples:
        # The MeteoFetch executor stores either a typed WeatherSample
        # (preferred) or an already-typed RainfallSample. Both expose
        # ``timestamp`` + ``precipitation_mm``; we duck-type on those
        # attributes so the assembler stays decoupled from Open-Meteo
        # specifics.
        ts = getattr(s, "timestamp", None)
        precip = getattr(s, "precipitation_mm", None)
        if ts is None or precip is None:
            continue
        samples.append(RainfallSample(timestamp=ts, precipitation_mm=float(precip)))
    return RainfallSeries(samples=tuple(samples))


def assemble_bundles(
    ctx: MonitoringContext,
    *,
    macroregion: str = "italy_default",
) -> Sequence[CellFeatureBundle]:
    """Return one :class:`CellFeatureBundle` per cell in the context.

    Missing snapshots degrade gracefully — they translate into ``None``
    fields on the bundle, and the deterministic engine treats those as
    neutral (0 for normalised factors, sigmoid midpoint for the
    soil/API sigmoids).
    """
    rainfall = _rainfall_series(ctx)
    seismic: tuple[SeismicHistoryEvent, ...] = tuple(ctx.seismic_events)

    bundles: list[CellFeatureBundle] = []
    for cell_id in ctx.cell_ids:
        sf = ctx.static_by_cell.get(cell_id) or StaticFactors(cell_id=cell_id)
        dyn = DynamicInputs(
            valuation_time=ctx.valuation_time,
            rainfall=rainfall,
            api_30_mm=ctx.api_30_mm,
            soil_moisture_0_7=ctx.soil_moisture_0_7,
            seismic_history=seismic,
            months_since_fire=ctx.months_since_fire,
            sensor_features=ctx.sensor_features_by_cell.get(cell_id),
        )
        bundles.append(
            CellFeatureBundle(
                aoi_id=ctx.aoi_id,
                cell_id=cell_id,
                static=sf,
                dynamic=dyn,
                macroregion=macroregion,
            )
        )
    return bundles
