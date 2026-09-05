"""CLMS Imperviousness Density → per-cell sealed fraction (#63).

One number per cell: the mean share of sealed surface, in [0, 1]. It
amplifies the **pluvial** branch of flood scoring and nothing else — concrete
does not make a river rise, it makes the same rain run off instead of soaking
in, which is the urban flash-flood mechanism.

Runs from ``limen bootstrap-static`` when ``LIMEN_IMPERVIOUSNESS_RASTER``
points at a GeoTIFF, and is a clean no-op with a structured log otherwise —
the same contract as the DEM and CORINE steps. Low cadence: the CLMS layer
refreshes every three years, and this is never on the hourly path.

Source: https://land.copernicus.eu/en/products/high-resolution-layer-imperviousness
"""

from limen.integrations.imperviousness.sync_job import (
    IMPERVIOUSNESS_RASTER_ENV,
    sync_imperviousness_for_aois,
)

__all__ = ["IMPERVIOUSNESS_RASTER_ENV", "sync_imperviousness_for_aois"]
