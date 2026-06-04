"""Per-cell InSAR feature aggregates derived from Copernicus EGMS (V2.1).

EGMS releases ~yearly, so this is a low-cadence table — the rollover
job runs once per ``egms.refresh_days``. Reads feed the V2 ML
:class:`MLScoringEngine` feature vector (strong predictor for
slow/DSGSD-class landslides).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from limen.core.logging import get_logger
from limen.data.db import acquire

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CellInsarFeatures:
    cell_id: str
    insar_velocity_mmy: float | None = None
    insar_accel_mmy2: float | None = None
    scatterer_count: int = 0
    period_start: date | None = None
    period_end: date | None = None
    dataset_version_id: int | None = None


async def upsert_many(items: Iterable[CellInsarFeatures]) -> int:
    rows = list(items)
    if not rows:
        return 0
    async with acquire() as conn, conn.transaction():
        for it in rows:
            await conn.execute(
                """
                INSERT INTO cell_insar_features (
                    cell_id, insar_velocity_mmy, insar_accel_mmy2,
                    scatterer_count, period_start, period_end, dataset_version_id
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (cell_id) DO UPDATE
                SET insar_velocity_mmy = EXCLUDED.insar_velocity_mmy,
                    insar_accel_mmy2   = EXCLUDED.insar_accel_mmy2,
                    scatterer_count    = EXCLUDED.scatterer_count,
                    period_start       = EXCLUDED.period_start,
                    period_end         = EXCLUDED.period_end,
                    dataset_version_id = EXCLUDED.dataset_version_id,
                    updated_at         = now()
                """,
                it.cell_id,
                it.insar_velocity_mmy,
                it.insar_accel_mmy2,
                it.scatterer_count,
                it.period_start,
                it.period_end,
                it.dataset_version_id,
            )
    log.info("cell_insar_features.upsert_many", count=len(rows))
    return len(rows)


async def get_for_cell(cell_id: str) -> CellInsarFeatures | None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT cell_id, insar_velocity_mmy, insar_accel_mmy2,
                   scatterer_count, period_start, period_end, dataset_version_id
            FROM cell_insar_features
            WHERE cell_id = $1
            """,
            cell_id,
        )
    if row is None:
        return None
    return CellInsarFeatures(
        cell_id=row["cell_id"],
        insar_velocity_mmy=row["insar_velocity_mmy"],
        insar_accel_mmy2=row["insar_accel_mmy2"],
        scatterer_count=int(row["scatterer_count"]),
        period_start=row["period_start"],
        period_end=row["period_end"],
        dataset_version_id=row["dataset_version_id"],
    )


__all__ = ["CellInsarFeatures", "get_for_cell", "upsert_many"]
