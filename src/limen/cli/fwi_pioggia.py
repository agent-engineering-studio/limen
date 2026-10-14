"""``limen fwi-pioggia`` — la catena FWI rifatta con la pioggia misurata dal DPC.

Lo stesso lavoro del passo notturno ``fwi_pioggia_osservata``, su un
intervallo a scelta: serve a ricostruire la stagione dopo averla accesa.
Il passo notturno rifà solo gli ultimi giorni.

Env: ``LIMEN_FWI_PIOGGIA_DAL`` / ``_AL`` (date ISO; default gli ultimi
``fwi.observed_rain.days`` giorni) e ``LIMEN_FWI_PIOGGIA_FONTE``: ``dpc``
(l'API, circa cinque mesi) o ``archivio`` (``RADAR_ARCHIVE__CARTELLA``).
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from limen.cli.fwi_backfill import params_from
from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.core.models.hazard import HazardType
from limen.core.scoring.regional_thresholds import WildfireThresholds, load_hazard_thresholds
from limen.data.db import lifespan_pool
from limen.integrations._http import SharedHttpClient
from limen.integrations.dpc.fwi_pioggia import Fonte, correggi, fonte_archivio, fonte_dpc
from limen.integrations.dpc.merging_archive import MergingArchive

log = get_logger(__name__)


async def run() -> int:
    t = load_hazard_thresholds(HazardType.WILDFIRE)
    assert isinstance(t, WildfireThresholds)
    cfg = t.fwi.observed_rain
    if cfg is None:
        log.error("fwi_pioggia.non_configurata", hint="fwi.observed_rain in wildfire.yaml")
        return 1
    oggi = datetime.now(UTC).date()
    dal = date.fromisoformat(
        os.getenv("LIMEN_FWI_PIOGGIA_DAL", "") or str(oggi - timedelta(days=cfg.days))
    )
    al = date.fromisoformat(os.getenv("LIMEN_FWI_PIOGGIA_AL", "") or str(oggi))
    nome = os.getenv("LIMEN_FWI_PIOGGIA_FONTE", "dpc")
    fonte: Fonte
    if nome == "archivio":
        archivio = get_settings().radar_archive
        if not archivio.attivo:
            log.error("fwi_pioggia.archivio_non_configurato", hint="RADAR_ARCHIVE__CARTELLA")
            return 1
        fonte = fonte_archivio(MergingArchive(Path(archivio.cartella)))
    elif nome == "dpc":
        fonte = fonte_dpc(cfg.max_step_mm)
    else:
        log.error("fwi_pioggia.fonte_sconosciuta", fonte=nome)
        return 1
    try:
        async with lifespan_pool():
            await correggi(dal=dal, al=al, params=params_from(t), fonte=fonte)
    finally:
        await SharedHttpClient.aclose()
    return 0
