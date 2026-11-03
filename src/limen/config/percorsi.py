"""La radice dei dati del deployment (#302).

``LIMEN_DATA_ROOT`` è una variabile dell'infrastruttura prima che dell'app: la
leggono i compose, il Makefile e gli script, che non passano da ``Settings``.
Qui la leggono i pochi default Python che scrivono o cercano file sotto di
essa, così che puntino dove la mettono anche gli altri. Vuota: ``data/``
relativa alla cartella di lavoro, come prima.
"""

from __future__ import annotations

import os
from pathlib import Path


def radice_dati() -> Path:
    return Path(os.environ.get("LIMEN_DATA_ROOT") or "data")


def cartella_geoserver() -> Path:
    """La cartella degli shapefile che ``geoserver-init`` carica.

    ``GEOSERVER_SHAPEFILE_DIR`` è la variabile che il compose monta: una sola
    manopola, perché chi scarica e chi carica devono guardare lo stesso posto.
    """
    return Path(os.environ.get("GEOSERVER_SHAPEFILE_DIR") or radice_dati() / "geoserver")


__all__ = ["cartella_geoserver", "radice_dati"]
