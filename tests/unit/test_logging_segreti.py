"""Le richieste HTTP non finiscono nei log: gli URL portano token e firme."""

from __future__ import annotations

import logging

from limen.core.logging import configure_logging


def test_httpx_non_scrive_le_richieste_a_info() -> None:
    configure_logging("INFO")
    assert not logging.getLogger("httpx").isEnabledFor(logging.INFO)
    assert logging.getLogger("httpx").isEnabledFor(logging.WARNING)


def test_a_debug_resta_spento_lo_stesso() -> None:
    configure_logging("DEBUG")
    assert not logging.getLogger("httpx").isEnabledFor(logging.INFO)
