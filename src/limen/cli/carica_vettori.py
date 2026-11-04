"""`limen carica-vettori` — i vettori ISPRA e ISTAT nel database di Limen (#426).

Carica nello schema ``sorgenti`` gli shapefile che ``geoserver-sync``,
``seed-comuni`` e il lookup dei comuni leggono (IFFI, mosaici PAI e
idraulico, confini dei comuni), dalla cartella in cui ``geodati-sync`` li
scarica. Dopo, con ``GEOSERVER_SOURCE__DB_DSN`` al database di Limen e
``GEOSERVER_SOURCE__SCHEMA_NAME=sorgenti``, GeoServer non serve più ai calcoli.

Rieseguibile: salta gli shapefile non cambiati (``LIMEN_VETTORI_FORZA=1`` o
``--forza`` per ricaricarli). Esce con 1 se uno non è entrato.
"""

from __future__ import annotations

import os

from limen.config.percorsi import cartella_geoserver
from limen.config.settings import get_settings
from limen.data.db import lifespan_pool
from limen.data.migrate import run_migrations
from limen.integrations.geoserver_source.vettori import carica_vettori

FORZA_ENV = "LIMEN_VETTORI_FORZA"


async def run() -> int:
    async with lifespan_pool(get_settings().db):
        await run_migrations()
        esito = await carica_vettori(cartella_geoserver(), forza=os.environ.get(FORZA_ENV) == "1")
    return 1 if esito.fallite else 0
