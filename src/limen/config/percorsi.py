"""La radice dei dati del deployment (#302).

``DATA_ROOT`` è una variabile dell'infrastruttura prima che dell'app: la
leggono i compose, il Makefile e gli script, che non passano da ``Settings``.
Qui la leggono i pochi default Python che scrivono o cercano file sotto di
essa, così che puntino dove la mettono anche gli altri. Vuota: ``data/``
relativa alla cartella di lavoro, come prima.

È la stessa radice delle librerie di agent-engineering-studio che scaricano
dati (ispra-idrogeo, egms-client, dpc-radar, firms-client): ognuna scrive in
``$DATA_ROOT/<pacchetto>``. Fino al 2026-11-25 si chiamava ``LIMEN_DATA_ROOT``,
che resta letta per un rilascio.
"""

from __future__ import annotations

import os
from pathlib import Path


def radice_dati() -> Path:
    return Path(os.environ.get("DATA_ROOT") or os.environ.get("LIMEN_DATA_ROOT") or "data")


def cartella_dataset() -> Path:
    """Cataloghi e archivi scaricati (e-ITALICA, FraneItalia).

    ``$DATA_ROOT/datasets``. ``LIMEN_DATA_DIR`` resta letta per un rilascio:
    era una seconda radice, ``./data`` per default, e sull'host metteva questi
    file nel repo invece che sotto ``DATA_ROOT``.
    """
    return Path(os.environ.get("LIMEN_DATA_DIR") or radice_dati() / "datasets").expanduser()


def cartella_geoserver() -> Path:
    """La cartella degli shapefile che ``geoserver-init`` carica.

    ``GEOSERVER_SHAPEFILE_DIR`` è la variabile che il compose monta: una sola
    manopola, perché chi scarica e chi carica devono guardare lo stesso posto.
    """
    return Path(os.environ.get("GEOSERVER_SHAPEFILE_DIR") or radice_dati() / "geoserver")


__all__ = ["cartella_dataset", "cartella_geoserver", "radice_dati"]
