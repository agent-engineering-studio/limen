"""``limen ingv-sync`` — terremoti INGV e scuotimento per cella dalle ShakeMap (#284).

Lo stesso lavoro del job orario, a mano. Scrivere `seismic_pga_cella` accende
la componente E delle frane al giro successivo, quindi il comando rifiuta
finché `SCHEDULER__ENABLE_INGV_SYNC` è spento: E non ha ancora il suo backtest
(#287). ``LIMEN_INGV_FORZA=1`` lo scavalca, per un database di prova.

Variabili d'ambiente: ``LIMEN_INGV_GIORNI`` (default `lookback_days` di
`landslide.yaml`), ``LIMEN_INGV_MAGNITUDO`` (default `min_magnitude`).
"""

from __future__ import annotations

import os

from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.core.scoring.regional_thresholds import load_regional_thresholds
from limen.data.db import lifespan_pool
from limen.integrations._http import SharedHttpClient
from limen.integrations.ingv.sync_job import run_ingv_sync

log = get_logger(__name__)


async def run() -> int:
    if not get_settings().scheduler.enable_ingv_sync and os.getenv("LIMEN_INGV_FORZA") != "1":
        log.error(
            "cli.ingv_sync.spento",
            motivo="scriverebbe la componente E, che non ha ancora il backtest (#287)",
            accendere="SCHEDULER__ENABLE_INGV_SYNC=true, oppure LIMEN_INGV_FORZA=1",
        )
        return 1
    seismic = load_regional_thresholds().seismic
    try:
        giorni = int(os.getenv("LIMEN_INGV_GIORNI", str(seismic.lookback_days)))
        magnitudo = float(os.getenv("LIMEN_INGV_MAGNITUDO", str(seismic.min_magnitude)))
    except ValueError:
        log.error("cli.ingv_sync.env_non_valida")
        return 1
    async with lifespan_pool():
        esito = await run_ingv_sync(
            bbox=get_settings().scheduler.ingv_bbox,
            lookback_days=giorni,
            min_magnitude=magnitudo,
        )
    await SharedHttpClient.aclose()
    log.info("cli.ingv_sync.done", **esito)
    return 0
