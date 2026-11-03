"""Copernicus EGMS, prodotto Ortho L3: la velocità del terreno per cella.

* :mod:`clms` — la chiave e l'archivio (download e cache da ``egms-client``);
* :mod:`aggregate` — mosaico e statistiche per cella, pure;
* :func:`sync_egms` — orchestrazione per AOI, idempotente su
  `dataset_versions`.
"""

from limen.integrations.egms.sync_job import sync_egms

__all__ = ["sync_egms"]
