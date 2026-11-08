"""HRL WaterWetness 2018 → quota di acqua e umido temporanei per cella (#420).

Un numero per cella in [0, 1]: la parte dei pixel classificati in cui il
satellite ha visto acqua o umido **temporanei** fra il 2009 e il 2015. Modula
la suscettibilità alluvionale delle sole celle dentro il mosaico idraulico
ISPRA (`flood.yaml`, blocco `water_wetness`): fra celle della stessa classe,
dice quali l'acqua la tengono davvero.

Gira da ``limen bootstrap-static`` quando ``LIMEN_WATER_WETNESS_RASTER``
punta a un GeoTIFF; senza, è uno skip pulito come DEM, CORINE e
impermeabilizzazione. Il raster lo scarica ``fetch.py`` dall'ImageServer
pubblico dell'EEA, senza account: ``limen water-wetness-fetch``.

Prodotto: https://land.copernicus.eu/en/products/high-resolution-layer-water-and-wetness
"""

from limen.integrations.water_wetness.fetch import fetch_water_wetness
from limen.integrations.water_wetness.sync_job import (
    WATER_WETNESS_RASTER_ENV,
    sync_water_wetness_for_aois,
)

__all__ = [
    "WATER_WETNESS_RASTER_ENV",
    "fetch_water_wetness",
    "sync_water_wetness_for_aois",
]
