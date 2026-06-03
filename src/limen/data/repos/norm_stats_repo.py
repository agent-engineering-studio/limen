"""Per-AOI min/max normalisation statistics, persisted for reproducibility."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from limen.data.db import acquire


@dataclass(frozen=True, slots=True)
class NormStat:
    aoi_id: str
    factor: str
    min_value: float
    max_value: float
    model_version: str
    sample_size: int | None = None
    extras: dict[str, Any] | None = None
    computed_at: datetime | None = None


async def upsert_many(items: Iterable[NormStat]) -> int:
    """Insert-or-update norm-stat rows."""
    items_list = list(items)
    if not items_list:
        return 0
    async with acquire() as conn, conn.transaction():
        for it in items_list:
            await conn.execute(
                """
                INSERT INTO norm_stats (
                    aoi_id, factor, min_value, max_value, model_version,
                    sample_size, extras
                ) VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
                ON CONFLICT (aoi_id, factor, model_version) DO UPDATE
                SET min_value   = EXCLUDED.min_value,
                    max_value   = EXCLUDED.max_value,
                    sample_size = EXCLUDED.sample_size,
                    extras      = EXCLUDED.extras,
                    computed_at = now()
                """,
                it.aoi_id,
                it.factor,
                it.min_value,
                it.max_value,
                it.model_version,
                it.sample_size,
                json.dumps(it.extras or {}, default=str),
            )
    return len(items_list)


async def fetch_for_aoi(
    aoi_id: str,
    *,
    model_version: str,
) -> list[NormStat]:
    """Fetch all norm stats for a given AOI + model version."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT aoi_id, factor, min_value, max_value, model_version,
                   sample_size, extras, computed_at
            FROM norm_stats WHERE aoi_id = $1 AND model_version = $2
            """,
            aoi_id,
            model_version,
        )
    out: list[NormStat] = []
    for r in rows:
        extras = r["extras"]
        if isinstance(extras, str):
            extras = json.loads(extras)
        out.append(
            NormStat(
                aoi_id=r["aoi_id"],
                factor=r["factor"],
                min_value=float(r["min_value"]),
                max_value=float(r["max_value"]),
                model_version=r["model_version"],
                sample_size=r["sample_size"],
                extras=extras or {},
                computed_at=r["computed_at"],
            )
        )
    return out
