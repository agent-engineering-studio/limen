"""``limen ems-verdetti`` — i verdetti radar sulle mappe EMS, dai file al database (#713).

Legge i rapporti che ``copernicus-ems`` scrive accanto alle coppie Sentinel-1,
``$DATA_ROOT/copernicus-ems/<CODICE>/sentinel-1/<stem>_quality.json`` e
``_agreement.json`` (+ ``.geojson``), e li scrive in ``ems_verdetti``,
``ems_acqua_confermata`` e ``ems_acqua_possibile``. Nessuna rete.

Rieseguibile: l'impronta del contenuto letto va in ``dataset_versions`` e un
giro con gli stessi file non scrive niente. Dice sempre due elenchi, perché
nessuna mappa deve sparire in silenzio: i rapporti di prodotti che Limen non
ha in ``flood_events`` / ``flood_observation_masks`` (scritti lo stesso), e i
prodotti di Limen senza alcun rapporto (che il backtest tiene come sono).
"""

from __future__ import annotations

import json
import os

from limen.config.percorsi import radice_dati
from limen.core.logging import get_logger
from limen.data.db import lifespan_pool
from limen.data.migrate import run_migrations
from limen.data.repos import dataset_versions_repo, ems_verdetti_repo
from limen.integrations.copernicus_ems.verdetti import Rapporto, raccogli

log = get_logger(__name__)

SOURCE = "copernicus-ems"
DATASET = "ems_verdetti"
FORCE_ENV = "LIMEN_EMS_VERDETTI_FORZA"

#: Da aumentare quando cambia come si leggono i file: stessi file, righe diverse.
VERSIONE_CALCOLO = 1


def versione(rapporti: list[Rapporto]) -> str:
    """SHA-256 del JSON canonico di tutto ciò che si scrive."""
    righe = [f"v{VERSIONE_CALCOLO}"]
    for r in sorted(rapporti, key=lambda x: (x.activation_code, x.product)):
        q, a = r.qualita, r.accordo
        righe.append(
            json.dumps(
                {
                    "activation": r.activation_code,
                    "product": r.product,
                    "stem": r.stem,
                    "quality": None
                    if q is None
                    else [
                        q.verdict,
                        q.reason,
                        q.flags,
                        q.measurements,
                        q.thresholds,
                        q.gap_hours,
                        q.resolution_m,
                    ],
                    "agreement": None
                    if a is None
                    else [
                        a.computed,
                        a.reason,
                        a.independent,
                        a.km2,
                        a.scores,
                        a.quality_verdict,
                        a.gap_hours,
                        a.resolution_m,
                        a.geojson,
                    ],
                    "classes": {
                        k: [c.area_km2, c.geom.wkb_hex] for k, c in sorted(r.classi.items())
                    },
                },
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
        )
    return dataset_versions_repo.content_hash(righe)


def confronta(rapporti: list[Rapporto], noti: set[str]) -> tuple[list[str], list[str]]:
    """(rapporti senza prodotto in Limen, prodotti di Limen senza rapporto)."""
    con_rapporto = {r.mask_id for r in rapporti}
    sconosciuti = sorted(
        f"{r.activation_code} {r.product}" for r in rapporti if r.mask_id not in noti
    )
    senza = sorted(noti - con_rapporto)
    return sconosciuti, senza


async def run() -> int:
    radice = radice_dati() / "copernicus-ems"
    forzato = os.environ.get(FORCE_ENV, "").strip().lower() in {"1", "true", "yes"}
    rapporti = raccogli(radice)
    async with lifespan_pool():
        await run_migrations()
        noti = await ems_verdetti_repo.prodotti_ems()
        sconosciuti, senza = confronta(rapporti, noti)
        for voce in sconosciuti:
            log.warning("ems_verdetti.prodotto_non_in_limen", prodotto=voce)
        if senza:
            log.info("ems_verdetti.prodotti_senza_rapporto", count=len(senza), prodotti=senza)
        if not rapporti:
            log.warning("ems_verdetti.nessun_rapporto", cartella=str(radice))
            return 0
        impronta = versione(rapporti)
        if not forzato and await dataset_versions_repo.find(SOURCE, DATASET, impronta):
            log.info("ems_verdetti.invariato", version=impronta[:12], rapporti=len(rapporti))
            return 0
        n = await ems_verdetti_repo.upsert_many(rapporti)
        conti = {
            v: sum(1 for r in rapporti if r.verdict == v)
            for v in ("coherent", "to check", "not assessable")
        }
        await dataset_versions_repo.record(
            source=SOURCE,
            dataset=DATASET,
            version=impronta,
            metadata={"rapporti": n, "senza_rapporto": len(senza), **conti},
        )
        log.info(
            "ems_verdetti.done",
            rapporti=n,
            verdetti=conti,
            non_in_limen=len(sconosciuti),
            senza_rapporto=len(senza),
        )
    return 0


__all__ = ["confronta", "run", "versione"]
