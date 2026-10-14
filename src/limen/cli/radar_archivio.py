"""``limen radar-archivio`` — salva il radar DPC «Merging» prima che il DPC lo perda.

Lo stesso lavoro del passo notturno ``radar_archivio``, a comando: serve al
primo recupero dei mesi che il DPC tiene ancora, senza aspettare le notti.
Legge ``RADAR_ARCHIVE__CARTELLA`` / ``__GIORNI``; ``LIMEN_RADAR_MASSIMO``
alza il tetto di file per esecuzione (default: tutti quelli che mancano).
"""

from __future__ import annotations

import os
from pathlib import Path

from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient
from limen.integrations.dpc.merging_archive import archivia

log = get_logger(__name__)


async def run() -> int:
    cfg = get_settings().radar_archive
    if not cfg.attivo:
        log.error("radar_archivio.non_configurato", hint="RADAR_ARCHIVE__CARTELLA")
        return 1
    massimo = int(os.getenv("LIMEN_RADAR_MASSIMO", "1000000"))
    try:
        conti = await archivia(Path(cfg.cartella), giorni=cfg.giorni, massimo=massimo)
    finally:
        await SharedHttpClient.aclose()
    return 0 if conti["falliti"] == 0 else 1
