"""Copernicus EGMS, prodotto Ortho L3: la velocità del terreno per cella.

* :mod:`client` — le tile da 100 km del portale (solo il GeoTIFF);
* :mod:`aggregate` — mosaico e statistiche per cella, pure;
* :func:`sync_egms` — orchestrazione per AOI, idempotente su
  `dataset_versions`.
"""

from limen.integrations.egms.sync_job import sync_egms

__all__ = ["sync_egms"]
