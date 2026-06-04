"""DEM-derivative pipeline (§3.3 TINITALY).

Three responsibilities:

* :mod:`derivatives` — pure numpy implementations of slope / aspect /
  curvature from a DEM array. No I/O, fully unit-testable on synthetic
  rasters.
* :mod:`zonal` — read a GeoTIFF + reproject a cell polygon into the
  raster CRS, compute the per-cell mean over each derivative.
* :mod:`sync_job` — orchestrator: ``limen bootstrap-static`` wires it
  in so the same one-shot CLI also fills the DEM-derived columns of
  ``cell_static_factors`` when ``LIMEN_DEM_RASTER`` points at a TIF.

The official input is `TINITALY 10 m` (INGV); the loader is parametric
on the raster path so any equivalent DEM (e.g. EU-DEM, regional 5 m
LiDAR mosaics) works without code changes.
"""

from limen.integrations.dem.derivatives import (
    aspect_deg,
    curvature,
    slope_deg,
)
from limen.integrations.dem.sync_job import sync_dem_for_aois
from limen.integrations.dem.zonal import CellDemStats, compute_cell_stats

__all__ = [
    "CellDemStats",
    "aspect_deg",
    "compute_cell_stats",
    "curvature",
    "slope_deg",
    "sync_dem_for_aois",
]
