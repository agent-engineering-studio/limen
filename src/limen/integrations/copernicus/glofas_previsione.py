"""La previsione GloFAS dall'EWDS, una corsa al giorno, in `glofas_previsione`.

GloFAS gira una volta al giorno (00 UTC). Il passo prova la corsa di oggi e,
se l'EWDS non l'ha ancora, quella di ieri; una corsa già salvata non si
riscarica. Gira in testa alla previsione per cella (02/08/14/20 UTC): alle 02
prende di solito la corsa del giorno prima, nei giri dopo quella del giorno.

Solo i nodi con un fiume (`glofas_riferimento.portata > 0`): per gli altri il
rapporto sarebbe comunque «non so».
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from limen.config.settings import Settings
from limen.core.logging import get_logger
from limen.core.models.hazard import HazardType
from limen.core.scoring.regional_thresholds import FloodThresholds, load_hazard_thresholds
from limen.data.repos import glofas_repo
from limen.integrations.copernicus import ewds_glofas

log = get_logger(__name__)

FONTE = "ewds:operational"


async def aggiorna(settings: Settings, *, oggi: date | None = None) -> dict[str, Any]:
    """Scarica e salva la corsa più recente che manca. Non alza mai."""
    cfg = settings.copernicus
    if not cfg.attivo or cfg.ewds_key is None:
        return {"status": "skipped", "reason": "COPERNICUS__EWDS_KEY non impostata"}
    oggi = oggi or datetime.now(UTC).date()
    try:
        ultima = await glofas_repo.ultima_corsa()
        if ultima is not None and ultima >= oggi:
            return {"status": "ok", "corsa": ultima.isoformat(), "salvati": 0}
        flood = load_hazard_thresholds(HazardType.FLOOD)
        assert isinstance(flood, FloodThresholds)
        nodi = await glofas_repo.nodi_con_fiume(
            percentile=flood.fluvial.reference_percentile,
            window_days=flood.fluvial.reference_window_days,
        )
        if not nodi:
            return {"status": "skipped", "reason": "nessun riferimento con un fiume"}
        client = ewds_glofas.nuovo_client(cfg.ewds_url, cfg.ewds_key.get_secret_value())
        cartella = Path(cfg.cartella)
        for corsa in (oggi, oggi - timedelta(days=1)):
            if ultima is not None and ultima >= corsa:
                break
            try:
                path = await asyncio.wait_for(
                    asyncio.to_thread(
                        ewds_glofas.scarica_previsione, cartella, corsa, client=client
                    ),
                    timeout=cfg.attesa_massima_secondi,
                )
            except Exception as exc:
                # La corsa di oggi non ancora pubblicata è il caso normale
                # dei giri del mattino: si prova quella di ieri.
                log.info(
                    "ewds.glofas.previsione.non_disponibile",
                    corsa=corsa.isoformat(),
                    error=str(exc)[:300],
                    error_type=type(exc).__name__,
                )
                continue
            picchi = await asyncio.to_thread(ewds_glofas.picchi_per_nodo, path, nodi)
            salvati = await glofas_repo.salva_previsione(corsa, picchi, fonte=FONTE)
            log.info(
                "ewds.glofas.previsione.salvata",
                corsa=corsa.isoformat(),
                nodi=len(nodi),
                salvati=salvati,
            )
            return {"status": "ok", "corsa": corsa.isoformat(), "salvati": salvati}
    except Exception as exc:
        log.warning(
            "integration.degraded",
            label="ewds.glofas.previsione",
            error=str(exc)[:300],
            error_type=type(exc).__name__,
        )
        return {"status": "error", "error": str(exc)[:300]}
    return {"status": "ok", "corsa": ultima.isoformat() if ultima else None, "salvati": 0}
