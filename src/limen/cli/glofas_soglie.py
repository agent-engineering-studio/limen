"""``limen glofas-soglie`` — le soglie GloFAS dei periodi di ritorno per nodo (#522).

Scarica una volta i tre file ufficiali (piena da 2, 5 e 20 anni, ~500 MB in
tutto, pubblici) in ``$LIMEN_DATA_ROOT/archivio/glofas-soglie`` e scrive in
``glofas_soglie`` la soglia della cella GloFAS di ogni nodo con un fiume (quelli
con una portata ordinaria in ``glofas_riferimento``). Rilanciabile: un file già
scaricato non si riscarica, e si leggono solo i nodi che non le hanno ancora:
gira anche ogni notte, dopo il riempimento dei riferimenti, che aggiunge nodi.

Servono all'etichetta «sopra la piena da N anni» nel riquadro della cella;
il punteggio non le legge.
"""

from __future__ import annotations

import asyncio

from limen.config.percorsi import radice_dati
from limen.core.logging import get_logger
from limen.core.models.hazard import HazardType
from limen.core.scoring.regional_thresholds import FloodThresholds, load_hazard_thresholds
from limen.data.db import lifespan_pool
from limen.data.repos import glofas_repo
from limen.integrations.copernicus import glofas_soglie

log = get_logger(__name__)


async def carica() -> int:
    flood = load_hazard_thresholds(HazardType.FLOOD)
    assert isinstance(flood, FloodThresholds)
    nodi = await glofas_repo.nodi_con_fiume(
        percentile=flood.fluvial.reference_percentile,
        window_days=flood.fluvial.reference_window_days,
    )
    fatti = await glofas_repo.nodi_con_soglie()
    nodi = [n for n in nodi if (round(n[0], 4), round(n[1], 4)) not in fatti]
    if not nodi:
        log.info("glofas_soglie.invariato", nodi_con_soglie=len(fatti))
        return 0
    files = await glofas_soglie.scarica(radice_dati() / "archivio" / "glofas-soglie")
    soglie = await asyncio.to_thread(glofas_soglie.soglie, files, nodi)
    scritte = await glofas_repo.salva_soglie(soglie, fonte=glofas_soglie.FONTE)
    senza = sum(1 for s in soglie.values() if s[0] is None)
    log.info("glofas_soglie.done", nodi=len(nodi), scritte=scritte, senza_soglia=senza)
    return scritte


async def run() -> int:
    async with lifespan_pool():
        await carica()
    return 0


__all__ = ["carica", "run"]
