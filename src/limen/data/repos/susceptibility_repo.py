"""Susceptibility repository.

Two storage modes coexist:

* **Per-cell** (``susceptibility`` table, populated by the scoring engine
  in Phase 3 and by the static-bootstrap pipeline): one row per grid cell.
* **Source polygons** (``susceptibility_polys`` was *not* introduced in
  Phase 1 — instead the ISPRA susceptibility layer is normalised
  cell-by-cell at ingest time so the table stays small).

This module exposes :func:`upsert_cells` for batch writes from either
the bootstrap pipeline or the ISPRA sync job.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from limen.core.logging import get_logger
from limen.data.db import acquire

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CellSusceptibility:
    cell_id: str
    score: float
    class_: str
    model_version: str
    inputs: dict[str, Any] | None = None


async def upsert_cells(items: Iterable[CellSusceptibility]) -> int:
    """Insert-or-update per-cell susceptibility rows in a single transaction."""
    items_list = list(items)
    if not items_list:
        return 0
    async with acquire() as conn, conn.transaction():
        for item in items_list:
            await conn.execute(
                """
                INSERT INTO susceptibility (cell_id, score, class, model_version, inputs)
                VALUES ($1, $2, $3, $4, $5::jsonb)
                ON CONFLICT (cell_id) DO UPDATE
                SET score         = EXCLUDED.score,
                    class         = EXCLUDED.class,
                    model_version = EXCLUDED.model_version,
                    inputs        = EXCLUDED.inputs,
                    computed_at   = now()
                """,
                item.cell_id,
                item.score,
                item.class_,
                item.model_version,
                json.dumps(item.inputs or {}, default=str),
            )
    log.info("susceptibility.upsert_cells", count=len(items_list))
    return len(items_list)


async def count_cells() -> int:
    async with acquire() as conn:
        row = await conn.fetchrow("SELECT COUNT(*)::bigint AS n FROM susceptibility")
    return int(row["n"]) if row else 0


async def get_for_cell(cell_id: str) -> CellSusceptibility | None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT cell_id, score, class, model_version, inputs FROM susceptibility WHERE cell_id = $1",
            cell_id,
        )
    if row is None:
        return None
    inputs = row["inputs"]
    if isinstance(inputs, str):
        inputs = json.loads(inputs)
    return CellSusceptibility(
        cell_id=row["cell_id"],
        score=float(row["score"]),
        class_=row["class"],
        model_version=row["model_version"],
        inputs=inputs or {},
    )
