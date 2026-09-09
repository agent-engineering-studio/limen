"""`limen train` — extract samples then run the ML training pipeline.

``LIMEN_TRAIN_HAZARD`` sceglie il pericolo:

* ``landslide`` (default) — arricchimento pioggia CERRA + addestramento;
* ``wildfire`` (#68) — arricchimento della catena FWI + addestramento, con il
  suo schema di feature e la baseline FWI-only;
* ``flood`` (#64) — estrae **solo** i campioni: il feature store sa già
  etichettare gli allagamenti osservati, ma nessuna pipeline di
  addestramento è modellata su quel pericolo, e usare quella delle frane
  darebbe un modello che misura un altro fenomeno.

La promozione resta manuale per tutti.
"""

from __future__ import annotations

import os

from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.core.models.hazard import DEFAULT_HAZARD, HazardType
from limen.data.db import lifespan_pool
from limen.data.migrate import run_migrations
from limen.ml.feature_store import extract_training_samples
from limen.ml.rain_features import enrich_rain_features
from limen.ml.train import run_training

log = get_logger(__name__)


def _hazard() -> HazardType:
    raw = os.getenv("LIMEN_TRAIN_HAZARD", "").strip()
    if not raw:
        return DEFAULT_HAZARD
    try:
        return HazardType(raw)
    except ValueError:
        log.warning("train.bad_hazard", value=raw)
        return DEFAULT_HAZARD


async def run() -> int:
    """CLI entry point — return process exit code."""
    settings = get_settings()
    hazard = _hazard()
    async with lifespan_pool(settings.db):
        await run_migrations()
        written = await extract_training_samples(settings=settings, hazard=hazard)
        log.info("train.samples_extracted", count=written, hazard=hazard.value)
        if hazard is HazardType.WILDFIRE:
            # L'incendio ha il suo enricher: il FWI del giorno va ricostruito
            # camminando la catena, e senza quello i campioni entrerebbero con
            # zero — cioè con la lezione sbagliata (#68).
            from limen.ml.fire_features import enrich_fire_features

            enriched = await enrich_fire_features()
            log.info("train.fire_enriched", count=enriched)
        elif hazard is not DEFAULT_HAZARD:
            log.info(
                "train.extract_only",
                hazard=hazard.value,
                note="pipeline di addestramento disponibile solo per landslide e wildfire",
            )
            return 0
        else:
            enriched = await enrich_rain_features()
            log.info("train.rain_enriched", count=enriched)
        if written == 0:
            log.warning(
                "train.no_samples",
                hint="seed IFFI via `limen` (Phase 2 sync) before training",
            )
            return 0
        result = await run_training(settings=settings, hazard=hazard)
        log.info(
            "train.done",
            run_id=result.run_id,
            auc_pr_mean=result.auc_pr_mean,
            baseline_auc_pr=result.baseline_auc_pr,
            promoted=result.promoted,
        )
    return 0
