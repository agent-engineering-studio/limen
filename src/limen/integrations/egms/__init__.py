"""Copernicus EGMS InSAR integration (V2.1).

Public surface:

* :class:`EgmsClient` — async HTTP client for the EGMS download
  portal. Returns the persistent-scatterer feature collection for a
  given AOI bbox.
* :func:`aggregate_scatterers_to_cells` — pure function that joins
  scatterers to ``grid_cells`` and computes the per-cell velocity +
  acceleration aggregates (degrades to zero counts when no points
  fall in a cell).
* :func:`sync_egms` — orchestrator: fetch → aggregate → upsert into
  ``cell_insar_features`` + register the dataset version.
"""

from limen.integrations.egms.aggregate import aggregate_scatterers_to_cells
from limen.integrations.egms.client import EgmsClient, ScattererPoint
from limen.integrations.egms.sync_job import sync_egms

__all__ = [
    "EgmsClient",
    "ScattererPoint",
    "aggregate_scatterers_to_cells",
    "sync_egms",
]
