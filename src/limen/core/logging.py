"""Structured logging configuration via structlog.

Call :func:`configure_logging` exactly once at the entry point (CLI, web app,
worker). Library code must only call ``structlog.get_logger(__name__)``.
"""

from __future__ import annotations

import logging
import sys

import structlog
from structlog.types import Processor


def configure_logging(level: str = "INFO", json_output: bool = False) -> None:
    """Configure stdlib + structlog logging.

    Args:
        level: Log level name (``"INFO"``, ``"DEBUG"``, ...).
        json_output: If true, emit JSON-formatted logs (good for production).
    """
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level.upper(),
    )
    # httpx scrive a INFO ogni richiesta con l'URL intero, query compresa: il
    # token di EGMS (`?id=`), la chiave FIRMS nel percorso, le firme degli URL
    # S3 del radar DPC finivano nei log del worker. Gli errori restano: li
    # riportano le integrazioni, con un'etichetta e senza l'URL.
    for rumoroso in ("httpx", "httpcore"):
        logging.getLogger(rumoroso).setLevel(
            max(logging.WARNING, logging.getLevelName(level.upper()))
        )

    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: Processor = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())
    )

    structlog.configure(
        processors=[*shared, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger bound to ``name``."""
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
