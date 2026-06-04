"""ISPRA Carta Geologica → per-cell ``lithology`` + ``dist_faults_m``.

Two-shapefile contract:

* ``lithology`` polygons — read the dominant class (by intersection
  area) per cell and map it to a normalised ``litho_weight`` via a
  lookup table (see :data:`LITHO_WEIGHTS`).
* ``faults`` lines (optional) — compute the geodesic distance from
  each cell centroid to the nearest fault, capped at 50 km.

Both shapefiles can be in any CRS; we reproject to EPSG:4326 once.
"""

from limen.integrations.geological.litho_weights import LITHO_WEIGHTS, normalise_litho
from limen.integrations.geological.sync_job import sync_geological_for_aois
from limen.integrations.geological.zonal import (
    CellGeologicalStats,
    compute_geological_stats,
)

__all__ = [
    "LITHO_WEIGHTS",
    "CellGeologicalStats",
    "compute_geological_stats",
    "normalise_litho",
    "sync_geological_for_aois",
]
