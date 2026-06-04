"""`limen train` — extract samples then run the ML training pipeline."""

from __future__ import annotations

from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.data.db import lifespan_pool
from limen.data.migrate import run_migrations
from limen.ml.feature_store import extract_training_samples
from limen.ml.train import run_training

log = get_logger(__name__)


async def run() -> int:
    """CLI entry point — return process exit code."""
    settings = get_settings()
    async with lifespan_pool(settings.db):
        await run_migrations()
        written = await extract_training_samples(settings=settings)
        log.info("train.samples_extracted", count=written)
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
