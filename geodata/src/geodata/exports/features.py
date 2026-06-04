"""Export per-cell static features to the operational DB — Stage C placeholder."""

from __future__ import annotations

import structlog

_log: structlog.stdlib.BoundLogger = structlog.get_logger("geodata.exports.features")


async def export_cell_features(*, operational_dsn: str) -> int:
    _log.warning(
        "geodata.export_features.not_implemented_yet",
        target=operational_dsn,
        hint="exporter lands in Stage C",
    )
    return 1
