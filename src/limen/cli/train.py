"""`limen train` — extract samples then run the ML training pipeline.

``LIMEN_TRAIN_HAZARD=flood`` estrae **solo** i campioni (#64): il feature
store sa già etichettare gli allagamenti osservati, ma `run_training` e
`enrich_rain_features` sono modellati sulle frane — finestre di pioggia
antecedente e feature InSAR di versante. Addestrare un challenger alluvione
con quella pipeline non darebbe un modello peggiore, darebbe un modello che
misura un altro fenomeno. I campioni restano pronti per quando la pipeline
del pericolo esisterà; la promozione resta manuale, come per tutti.
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
        if hazard is not DEFAULT_HAZARD:
            log.info(
                "train.extract_only",
                hazard=hazard.value,
                note="pipeline di addestramento disponibile solo per il pericolo di default",
            )
            return 0
        enriched = await enrich_rain_features()
        log.info("train.rain_enriched", count=enriched)
        if written == 0:
            log.warning(
                "train.no_samples",
                hint="seed IFFI via `limen` (Phase 2 sync) before training",
            )
            return 0
        result = await run_training(settings=settings)
        log.info(
            "train.done",
            run_id=result.run_id,
            auc_pr_mean=result.auc_pr_mean,
            baseline_auc_pr=result.baseline_auc_pr,
            promoted=result.promoted,
        )
    return 0
