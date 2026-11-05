"""``limen ems-sentinel1`` — coppie Sentinel-1 / etichette EMS, solo come dati per l'ML.

Per ogni prodotto alluvionale delle attivazioni già in ``flood_events``, la
libreria ``copernicus-ems`` sceglie il passaggio Sentinel-1 più vicino
all'osservazione, chiede al Copernicus Data Space il backscatter tagliato
sulla **stessa griglia** del raster di etichette, e scrive immagine, etichette
e ``_pair.json`` in ``COPERNICUS_EMS_DATA_DIR``. Con il riferimento (default)
anche il passaggio pre-evento della stessa orbita, per il change detection.

**Non entra nel punteggio, né nella mappa, né negli alert.** Sulle etichette
indipendenti (Pléiades/SPOT), lasciando fuori un'attivazione alla volta, la
soglia su VV arriva a un CSI di 0,12 e ogni rivelatore sovrastima (bias da 2
a 7): è materiale per addestrare un futuro challenger, non un segnale
osservato da mettere accanto al motore V1.

Le processing unit sono soldi di una quota: 10.000 al mese per un account
generico. Prima di spendere si sommano quelle che ``make_pair`` spenderebbe
davvero (``pu_to_spend``: le immagini già su disco valgono 0) a quelle già
spese nel mese, e oltre ``COPERNICUS__CDSE_PU_MENSILI`` non parte niente. La
spesa si registra in ``dataset_versions`` **prima** delle richieste: un giro
interrotto a metà conta qualcosa di troppo, mai di meno.

Ogni richiesta (catalogo, layer, STAC, token, Process API) passa da
``fetch_with_retry`` con l'hook ``send=``: la libreria non installa il suo
retry.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx

from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.data.db import lifespan_pool
from limen.data.migrate import run_migrations
from limen.data.repos import dataset_versions_repo, flood_events_repo
from limen.integrations._http import SharedHttpClient, fetch_with_retry

if TYPE_CHECKING:
    from copernicus_ems.sentinelhub import PairPlan, ReferencePlan

log = get_logger(__name__)

SOURCE = "copernicus-cdse"
DATASET = "sentinel1_pairs"

#: Il Process API taglia un'immagine per richiesta e può metterci minuti:
#: la lettura del client condiviso (60 s) la interromperebbe. 300 s è il
#: timeout che la libreria dà al suo client.
_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)

#: Il taglio del riferimento, come nella CLI della libreria: il passaggio
#: pre-evento deve precedere l'inizio dell'alluvione, non l'osservazione.
_PRIMA_DELL_EVENTO = timedelta(days=1)


async def _send(request: httpx.Request) -> httpx.Response:
    """La richiesta della libreria, così com'è, dentro la politica di retry di Limen."""
    return await fetch_with_retry(
        request.method,
        str(request.url),
        headers=request.headers,
        content=request.content,
        timeout=_TIMEOUT,
    )


def _inizio_mese(now: datetime) -> datetime:
    return now.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _da_scaricare(plans: Sequence[PairPlan], refs: Sequence[ReferencePlan | None]) -> list[str]:
    """I percorsi delle immagini non ancora su disco: l'identità della prenotazione."""
    paths = {
        p.backscatter_path
        for p in [*plans, *refs]
        if p is not None and p.scene_pass is not None and p.backscatter_path is not None
    }
    return sorted(str(p) for p in paths if not p.is_file())


async def esegui(
    *, dry_run: bool, codici: Sequence[str] = (), now: datetime | None = None
) -> dict[str, Any]:
    """Pianifica, controlla il budget, scarica. Il riepilogo; pool già aperto."""
    from copernicus_ems import RapidMapping
    from copernicus_ems.errors import EmsError
    from copernicus_ems.sentinelhub import (
        SentinelHub,
        make_pair,
        plan_pair,
        plan_reference,
        pu_to_spend,
    )

    cfg = get_settings().copernicus
    now = now or datetime.now(UTC)
    voluti = {c.upper() for c in codici}
    attivazioni = [
        a
        for a in await flood_events_repo.activations_summary()
        if not voluti or a.activation_code.upper() in voluti
    ]
    if not attivazioni:
        log.warning("ems_sentinel1.no_activations", codici=sorted(voluti))
        return {"esito": "nessuna_attivazione"}

    ems = RapidMapping(send=_send)
    try:
        plans: list[PairPlan] = []
        refs: dict[str, ReferencePlan] = {}
        for attivazione in attivazioni:
            # Solo le alluvioni (il filtro di default): con event_types=None le
            # frane della stessa pioggia diventerebbero «allagato» (la 0.5.0).
            for event in await ems.observed_events(attivazione.activation_code):
                if event.product.observed_time is None or event.product.aoi_extent is None:
                    continue
                plan = await plan_pair(ems, event, resolution_m=cfg.s1_risoluzione_m)
                plans.append(plan)
                if cfg.s1_riferimento and plan.scene_pass is not None:
                    refs[plan.product] = await plan_reference(
                        ems, plan, before=attivazione.event_time - _PRIMA_DELL_EVENTO
                    )
    finally:
        await ems.aclose()

    pronti = [p for p in plans if p.scene_pass is not None]
    for plan in plans:
        log.info(
            "ems_sentinel1.plan",
            product=plan.product,
            pass_found=plan.scene_pass is not None,
            reason=plan.reason,
            pu=round(plan.pu, 1),
            reference=refs[plan.product].scene_pass is not None if plan.product in refs else None,
        )
    da_spendere = pu_to_spend(plans, list(refs.values()))
    speso = await dataset_versions_repo.sum_metadata_since(SOURCE, DATASET, "pu", _inizio_mese(now))
    riepilogo: dict[str, Any] = {
        "attivazioni": len(attivazioni),
        "prodotti": len(plans),
        "coppie": len(pronti),
        "pu_da_spendere": round(da_spendere, 1),
        "pu_spese_nel_mese": round(speso, 1),
        "pu_mensili": cfg.cdse_pu_mensili,
    }
    if dry_run:
        return {"esito": "piano", **riepilogo}
    if speso + da_spendere > cfg.cdse_pu_mensili:
        log.error("ems_sentinel1.over_budget", **riepilogo)
        return {"esito": "oltre_budget", **riepilogo}

    nuove = _da_scaricare(pronti, [refs.get(p.product) for p in pronti])
    if nuove:
        await dataset_versions_repo.record(
            source=SOURCE,
            dataset=DATASET,
            # Il mese nella versione: la stessa prenotazione ripetuta il mese
            # dopo (giro interrotto) si conta nel mese in cui si spende.
            version=f"{now:%Y-%m}:" + dataset_versions_repo.content_hash(nuove),
            metadata={"pu": da_spendere, "immagini": len(nuove)},
        )

    scritte = 0
    fallite: list[str] = []
    async with SentinelHub(send=_send) as hub:
        for plan in pronti:
            try:
                # Le immagini già su disco non si richiedono: le etichette e il
                # manifest si riscrivono comunque, gratis.
                await make_pair(hub, plan, reference=refs.get(plan.product))
            except (EmsError, httpx.HTTPError, OSError) as exc:
                log.warning("ems_sentinel1.pair_failed", product=plan.product, error=str(exc))
                fallite.append(plan.product)
                continue
            scritte += 1
        stimate = hub.pu_estimated
    log.info("ems_sentinel1.done", scritte=scritte, fallite=len(fallite), pu_stimate=stimate)
    return {
        "esito": "scritto",
        **riepilogo,
        "scritte": scritte,
        "fallite": fallite,
        "pu_spese_ora": round(stimate, 1),
    }


async def run(*, dry_run: bool, codici: Sequence[str] = ()) -> int:
    try:
        async with lifespan_pool():
            await run_migrations()
            out = await esegui(dry_run=dry_run, codici=codici)
    finally:
        await SharedHttpClient.aclose()
    log.info("ems_sentinel1.summary", **out)
    if out["esito"] == "oltre_budget":
        return 2
    return 1 if out.get("fallite") else 0


def codici_da_env() -> list[str]:
    raw = os.getenv("LIMEN_EMS_S1_CODICI", "")
    return [c.strip() for c in raw.split(",") if c.strip()]
