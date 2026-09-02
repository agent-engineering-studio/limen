"""``limen firms-sync`` — ingest NASA FIRMS active-fire hotspots.

Fail-closed on ``FIRMS__MAP_KEY``: without a key the command reports the
missing configuration and exits non-zero rather than silently doing
nothing (a scheduled job stays quiet, an operator running a command
wants to know).

Idempotent: a second run over an unchanged FIRMS window matches the
recorded ``dataset_versions`` row and skips every write.

Env knobs: ``LIMEN_FIRMS_DAY_RANGE`` (1..5) and ``LIMEN_FIRMS_DATE``
(``YYYY-MM-DD``) to re-fetch a specific window.
"""

from __future__ import annotations

import os
from datetime import date

from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.data.db import lifespan_pool
from limen.data.migrate import run_migrations
from limen.integrations.firms import FirmsHttpClient, run_firms_sync

log = get_logger(__name__)


def _on_date() -> date | None:
    raw = os.getenv("LIMEN_FIRMS_DATE")
    if not raw:
        return None
    return date.fromisoformat(raw.strip())


async def run() -> int:
    settings = get_settings()
    cfg = settings.firms
    if cfg.map_key is None:
        log.error("firms_sync.no_map_key", hint="set FIRMS__MAP_KEY (free FIRMS registration)")
        return 1

    day_range = int(os.getenv("LIMEN_FIRMS_DAY_RANGE", str(cfg.day_range)))
    client = FirmsHttpClient(
        map_key=cfg.map_key.get_secret_value(),
        min_confidence=cfg.min_confidence,
        min_confidence_pct=cfg.min_confidence_pct,
        min_frp_mw=cfg.min_frp_mw,
    )
    async with lifespan_pool(settings.db):
        await run_migrations()
        result = await run_firms_sync(
            client=client,
            bbox=cfg.bbox,
            sources=cfg.sources,
            day_range=day_range,
            on_date=_on_date(),
        )
    log.info("firms_sync.done", **{k: v for k, v in result.items() if k != "version"})
    return 0
