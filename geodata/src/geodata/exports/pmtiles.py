"""``limen geodata make-pmtiles`` — Stage C placeholder."""

from __future__ import annotations

import structlog

_log: structlog.stdlib.BoundLogger = structlog.get_logger("geodata.exports.pmtiles")


async def make_pmtiles() -> int:
    _log.warning(
        "geodata.make_pmtiles.not_implemented_yet",
        hint="tippecanoe driver lands in Stage C",
    )
    return 1
