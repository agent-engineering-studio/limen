"""``limen glofas-ewds`` — la portata ordinaria dei nodi GloFAS dall'EWDS (#200).

Fa in un download quello che `glofas-riferimenti` fa in tre settimane di quota
Open-Meteo: scarica due anni di GloFAS 4 sull'Italia dall'Early Warning Data
Store di Copernicus, prende per ogni nodo la cella i cui valori Open-Meteo
restituisce e ne salva il percentile in `glofas_riferimento`, con
``fonte = 'ewds:version_4_0'``. Riempie solo i nodi che mancano; il notturno
li trova già fatti e non spende niente.

    uv run --group copernicus limen glofas-ewds

* ``COPERNICUS__EWDS_KEY`` — la chiave EWDS (in ``.env``); la licenza
  CEMS-Floods va accettata una volta sul sito.
* ``LIMEN_EWDS_DIR`` — dove tenere i file mensili (obbligatoria). Rilanciando,
  i mesi già scaricati non si richiedono.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.core.models.hazard import HazardType
from limen.core.scoring.regional_thresholds import FloodThresholds, load_hazard_thresholds
from limen.data.db import lifespan_pool
from limen.data.repos import glofas_repo
from limen.integrations.copernicus import ewds_glofas
from limen.integrations.openmeteo.flood import NODE_SPACING_DEG

log = get_logger(__name__)

#: Nessun limite: il download costa uguale per un nodo o per tutti.
_TUTTI = 1_000_000


async def run() -> int:
    cartella = os.getenv("LIMEN_EWDS_DIR")
    if not cartella:
        log.error("cli.glofas_ewds.manca_cartella", hint="imposta LIMEN_EWDS_DIR")
        return 2
    cfg = get_settings().copernicus
    if cfg.ewds_key is None or not cfg.attivo:
        log.error("cli.glofas_ewds.manca_chiave", hint="imposta COPERNICUS__EWDS_KEY")
        return 2
    client = ewds_glofas.nuovo_client(cfg.ewds_url, cfg.ewds_key.get_secret_value())
    flood = load_hazard_thresholds(HazardType.FLOOD)
    assert isinstance(flood, FloodThresholds)
    percentile = flood.fluvial.reference_percentile
    window_days = flood.fluvial.reference_window_days
    # La stessa finestra del riempimento da Open-Meteo: fino a ieri.
    fine = datetime.now(UTC).date() - timedelta(days=1)
    inizio = fine - timedelta(days=window_days)

    async with lifespan_pool():
        nodi = await glofas_repo.da_calcolare(
            spacing=NODE_SPACING_DEG,
            percentile=percentile,
            window_days=window_days,
            limite=_TUTTI,
            soglia_pioggia_mm=0.0,
        )
        if not nodi:
            log.info("cli.glofas_ewds.niente_da_fare")
            return 0
        # Ore di attesa in coda all'EWDS e qualche centinaio di MB da leggere:
        # in un thread, perché il pool resta aperto per il salvataggio.
        files = await asyncio.to_thread(
            ewds_glofas.scarica, Path(cartella), inizio, fine, client=client
        )
        serie = await asyncio.to_thread(
            ewds_glofas.serie_per_nodo, files, nodi, inizio=inizio, fine=fine
        )
        rif = ewds_glofas.riferimenti(serie, percentile=percentile)
        salvati = await glofas_repo.salva(
            list(rif.items()),
            percentile=percentile,
            window_days=window_days,
            fonte=ewds_glofas.FONTE,
        )
    con_fiume = sum(1 for p in rif.values() if p is not None and p > 0)
    log.info(
        "cli.glofas_ewds.done",
        nodi=len(nodi),
        salvati=salvati,
        con_fiume=con_fiume,
        mesi=len(files),
        inizio=inizio.isoformat(),
        fine=fine.isoformat(),
    )
    return 0
