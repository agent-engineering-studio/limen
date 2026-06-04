"""`limen ingest-kb` — push the local corpus to the knowledge-graph sidecar.

The corpus root defaults to ``LIMEN_KB_CORPUS`` (env) or ``./kb-corpus``.
Suffix-based discovery; see :func:`discover_documents` for the contract.
"""

from __future__ import annotations

import os
from pathlib import Path

from limen.config.settings import get_settings
from limen.core.logging import get_logger
from limen.data.db import lifespan_pool
from limen.data.migrate import run_migrations
from limen.knowledge.ingest import ingest_corpus

log = get_logger(__name__)


async def run() -> int:
    settings = get_settings()
    corpus_root = Path(os.environ.get("LIMEN_KB_CORPUS", "./kb-corpus"))
    async with lifespan_pool(settings.db):
        await run_migrations()
        result = await ingest_corpus(corpus_root=corpus_root, settings=settings)
        log.info(
            "ingest_kb.done",
            corpus_root=str(corpus_root),
            documents_seen=result.documents_seen,
            documents_sent=result.documents_sent,
            skipped_unchanged=result.skipped_unchanged,
        )
    return 0
