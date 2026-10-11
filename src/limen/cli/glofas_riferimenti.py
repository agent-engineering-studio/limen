"""``limen glofas-riferimenti`` — calcola la portata ordinaria dei nodi GloFAS (#200).

La pipeline notturna lo fa da sola, entro `SCHEDULER__GLOFAS_CHIAMATE_PER_NOTTE`
chiamate. Il comando serve a riempire la tabella prima, per esempio appena
dopo il deploy: si ferma al primo 429, e rilanciarlo il giorno dopo riprende
dai nodi che mancano.

Env: ``LIMEN_GLOFAS_CHIAMATE`` — chiamate dell'API da spendere (default 3000;
il tetto giornaliero è 10.000 e lo sweep ne ha bisogno).
"""

from __future__ import annotations

import os

from limen.core.logging import get_logger
from limen.core.models.hazard import HazardType
from limen.core.scoring.regional_thresholds import FloodThresholds, load_hazard_thresholds
from limen.data.db import lifespan_pool
from limen.integrations._http import SharedHttpClient
from limen.integrations.openmeteo.glofas_riferimenti import riempi

log = get_logger(__name__)


async def run() -> int:
    chiamate = int(os.getenv("LIMEN_GLOFAS_CHIAMATE", "3000"))
    flood = load_hazard_thresholds(HazardType.FLOOD)
    assert isinstance(flood, FloodThresholds)
    try:
        async with lifespan_pool():
            esito = await riempi(
                chiamate=chiamate,
                percentile=flood.fluvial.reference_percentile,
                window_days=flood.fluvial.reference_window_days,
            )
    finally:
        await SharedHttpClient.aclose()
    log.info("cli.glofas_riferimenti.done", **esito)
    return 0
