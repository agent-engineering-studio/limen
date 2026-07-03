"""Build one :class:`CellFeatureBundle` per cell from a workflow context.

Pure function: takes the snapshots already collected in
:class:`MonitoringContext` and shapes them into the engine's input
DTOs. No I/O. The executor layer is responsible for filling the
context; this is the deterministic glue.

Rainfall is per-cell when the context carries a rainfall-node grid
(``rain_nodes`` + ``rainfall_by_node`` from MeteoFetch): each cell gets the
series of its nearest node. Without a grid — or for a cell with no centroid
or an empty node series — it falls back to the single AOI-centroid series,
preserving the degradation invariant.

The same assembler feeds the V2 ML engine (`Limen_Project_Document.md`
§3.15), which is why the function is decoupled from any concrete scorer.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from limen.core.models.context import MonitoringContext
from limen.core.models.risk import (
    CellFeatureBundle,
    DynamicInputs,
    RainfallSample,
    RainfallSeries,
    SeismicHistoryEvent,
    StaticFactors,
)
from limen.integrations.openmeteo.grid import nearest_node


def _to_series(samples_in: Iterable[Any]) -> RainfallSeries:
    """Coerce (Open-Meteo-derived) samples into a typed series.

    MeteoFetch stores either a typed WeatherSample (preferred) or an
    already-typed RainfallSample. Both expose ``timestamp`` +
    ``precipitation_mm``; we duck-type on those attributes so the assembler
    stays decoupled from Open-Meteo specifics.
    """
    samples: list[RainfallSample] = []
    for s in samples_in:
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
    fallback = _to_series(ctx.meteo_samples)
    nodes = [(float(lon), float(lat)) for lon, lat in ctx.rain_nodes]
    node_series = [_to_series(series) for series in ctx.rainfall_by_node]
    use_grid = bool(nodes) and len(node_series) == len(nodes)
    seismic: tuple[SeismicHistoryEvent, ...] = tuple(ctx.seismic_events)

    bundles: list[CellFeatureBundle] = []
    for cell_id in ctx.cell_ids:
        rainfall = fallback
        if use_grid:
            centroid = ctx.cell_centroids.get(cell_id)
            if centroid is not None:
                series = node_series[nearest_node(centroid[0], centroid[1], nodes)]
                if series.samples:
                    rainfall = series
        sf = ctx.static_by_cell.get(cell_id) or StaticFactors(cell_id=cell_id)
        dyn = DynamicInputs(
            valuation_time=ctx.valuation_time,
            rainfall=rainfall,
            api_30_mm=ctx.api_30_mm,
            soil_moisture_0_7=ctx.soil_moisture_0_7,
            snow_depth_m=ctx.snow_depth_m,
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
