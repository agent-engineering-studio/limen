"""Persist per-cell forecast scores for the trend chart (issue #41).

Sweeps each AOI at +24/+48/+72 h and writes the **≥ Moderate** cells to
``risk_assessments`` with ``horizon="+Hh"`` and ``pipeline_version=
"v1-forecast+Hh"`` (``computed_at=now()`` → the UI derives the target time as
``computed_at + H``). Idempotent + bounded: the prior forecast rows for the same
cells at that horizon are deleted before the new insert, so only the latest
forecast per (cell, horizon) survives. The observed history keeps the
operational horizon (e.g. ``24h``); the two are read together by
``GET /api/cell/{id}/history``.
"""

from __future__ import annotations

import json
from typing import Any

from limen.agents.workflows.forecast import run_forecast
from limen.config.settings import Settings, get_settings
from limen.core.logging import get_logger
from limen.core.models.context import CellRiskRecord
from limen.core.models.risk import RiskLevel
from limen.data.db import acquire

log = get_logger(__name__)

# Persist only cells at/above this level — those shown in the list / report.
_LEVEL_ORDER = (
    RiskLevel.None_,
    RiskLevel.Low,
    RiskLevel.Moderate,
    RiskLevel.High,
    RiskLevel.VeryHigh,
)
_DEFAULT_FLOOR = RiskLevel.Moderate
_DEFAULT_HORIZONS = (24, 48, 72)

_DELETE_PRIOR_SQL = """
DELETE FROM risk_assessments
WHERE horizon = $1 AND cell_id = ANY($2::text[]) AND pipeline_version LIKE 'v1-forecast+%'
"""

_INSERT_SQL = """
INSERT INTO risk_assessments (
    cell_id, computed_at, horizon, score, class, factors,
    explanation, pipeline_version, dataset_versions
) VALUES ($1, now(), $2, $3, $4, $5::jsonb, '{}'::jsonb, $6, ARRAY[]::bigint[])
"""


def at_or_above(level: RiskLevel, floor: RiskLevel) -> bool:
    return _LEVEL_ORDER.index(level) >= _LEVEL_ORDER.index(floor)


def cells_to_persist(
    cell_results: list[CellRiskRecord], *, floor: RiskLevel = _DEFAULT_FLOOR
) -> list[CellRiskRecord]:
    """Pure: the cells worth persisting for the forecast trend (≥ floor)."""
    return [c for c in cell_results if at_or_above(c.level, floor)]


async def persist_forecast_run(
    conn: Any,
    horizon_h: int,
    cell_results: list[CellRiskRecord],
    *,
    floor: RiskLevel = _DEFAULT_FLOOR,
) -> int:
    """Write the ≥floor cells of one forecast run; delete prior rows first."""
    keep = cells_to_persist(cell_results, floor=floor)
    horizon = f"+{horizon_h}h"
    pipeline_version = f"v1-forecast+{horizon_h}h"
    cell_ids = [c.cell_id for c in keep]
    async with conn.transaction():
        await conn.execute(_DELETE_PRIOR_SQL, horizon, cell_ids)
        for c in keep:
            factors = {"s": c.s, "m": c.m, "e": c.e, "f": c.f, "h": c.h}
            await conn.execute(
                _INSERT_SQL,
                c.cell_id,
                horizon,
                c.score,
                c.level.value,
                json.dumps(factors, default=str),
                pipeline_version,
            )
    return len(keep)


async def run_forecast_history(
    *,
    aoi_ids: list[str] | None = None,
    horizons: tuple[int, ...] = _DEFAULT_HORIZONS,
    settings: Settings | None = None,
) -> int:
    """Sweep all AOIs at the given horizons and persist ≥Moderate forecast cells."""
    settings = settings or get_settings()
    floor = _DEFAULT_FLOOR
    if aoi_ids is None:
        async with acquire() as conn:
            rows = await conn.fetch("SELECT id FROM aoi ORDER BY id")
        aoi_ids = [str(r["id"]) for r in rows]

    total = 0
    for aoi_id in aoi_ids:
        for h in horizons:
            run = await run_forecast(aoi_id=aoi_id, horizon_h=h, settings=settings)
            async with acquire() as conn:
                n = await persist_forecast_run(conn, h, run.cell_results, floor=floor)
            total += n
            log.info("forecast_history.persisted", aoi_id=aoi_id, horizon_h=h, cells=n)
    log.info("forecast_history.done", aois=len(aoi_ids), horizons=list(horizons), cells=total)
    return total
