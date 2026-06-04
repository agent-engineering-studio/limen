"""CORINE Land Cover ingestion → per-cell dominant ``landuse_code``.

Copernicus CORINE Land Cover ships as a categorical raster (level-3
codes, 100 m pixels). For each Limen grid cell we read the masked
pixels, take the majority class, and upsert that as ``landuse_code``
in ``cell_static_factors``.

Like the DEM pipeline, the loader is parametric on the raster path
so the same code works against CLC2018, CLC2024, or a regional
refinement.
"""

from limen.integrations.corine.sync_job import sync_corine_for_aois
from limen.integrations.corine.zonal import (
    CellLandUseStats,
    compute_landuse_stats,
)

__all__ = [
    "CellLandUseStats",
    "compute_landuse_stats",
    "sync_corine_for_aois",
]
