"""`limen geodati-sync` — i dati geografici di base ISPRA per lo stack GeoServer.

Il primo giro scarica ~3 GB (IFFI regione per regione, mosaici PAI e
idraulico); i successivi chiedono a IdroGEO solo se qualcosa è cambiato.
Esce con 1 se un file non è arrivato: gli altri sono comunque al loro posto,
e il prossimo giro riprova solo quelli.
"""

from __future__ import annotations

from limen.config.settings import get_settings
from limen.integrations.idrogeo.geodati import sync_geodati


async def run() -> int:
    esito = await sync_geodati(get_settings().geodati)
    return 1 if esito.falliti else 0
