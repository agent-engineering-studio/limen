"""Ogni ora, i terremoti INGV della settimana e lo scuotimento per cella (#284).

Spento di default (`SCHEDULER__ENABLE_INGV_SYNC`): è ciò che dà un valore
alla componente E delle frane.
"""

from __future__ import annotations

from typing import Any

from limen.api.dependencies import AppDependencies
from limen.core.scoring.regional_thresholds import load_regional_thresholds
from limen.integrations.ingv.sync_job import run_ingv_sync


async def run_ingv_sync_job(deps: AppDependencies) -> dict[str, Any]:
    # Finestra e magnitudo dallo stesso YAML che il motore legge: scaricare
    # meno di quanto il motore considera lascerebbe buchi senza dirlo.
    seismic = load_regional_thresholds().seismic
    return await run_ingv_sync(
        bbox=deps.settings.scheduler.ingv_bbox,
        lookback_days=seismic.lookback_days,
        min_magnitude=seismic.min_magnitude,
    )
