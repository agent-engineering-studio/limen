"""`limen geodati-sync` — tutti gli shapefile che geoserver-init carica.

Il primo giro scarica ~3,3 GB: da IdroGEO l'IFFI regione per regione e i
mosaici PAI e idraulico, poi confini ISTAT, CORINE 2018 e geolitologia. I
giri successivi chiedono a IdroGEO solo se qualcosa è cambiato, e gli altri
tre, che non cambiano, non li chiedono più.
Esce con 1 se un file non è arrivato: gli altri sono comunque al loro posto,
e il prossimo giro riprova solo quelli.
"""

from __future__ import annotations

from limen.config.settings import get_settings
from limen.integrations.idrogeo.geodati import sync_geodati


async def run() -> int:
    esito = await sync_geodati(get_settings().geodati)
    return 1 if esito.falliti else 0
