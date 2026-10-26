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


__all__ = ["radice_dati"]
