"""Training-samples feature store (V2).

Writes are append-only via :func:`insert_many` (the spatial-block split
is computed offline by ``ml.feature_store`` and persisted with each
row). Reads support the training pipeline (one fold at a time).

The features blob is JSONB on the wire and a plain dict in Python.
Both V1 deterministic features (so V2 ML can train against the same
inputs) and V2-only extras (InSAR velocity, sensor aggregates) live
under the same JSONB key.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from limen.core.logging import get_logger
from limen.data.db import acquire

log = get_logger(__name__)

LabelSource = Literal["italica", "iffi", "background"]


@dataclass(frozen=True, slots=True)
class TrainingSample:
    cell_id: str
    valuation_time: datetime
    label: int
    label_source: LabelSource
    features: dict[str, Any]
    split_block: str
    dataset_version_id: int | None = None


async def insert_many(items: Iterable[TrainingSample]) -> int:
    rows = list(items)
    if not rows:
        return 0
    async with acquire() as conn, conn.transaction():
        for it in rows:
            await conn.execute(
                """
                INSERT INTO training_samples (
                    cell_id, valuation_time, label, label_source,
                    features, split_block, dataset_version_id
                ) VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
                ON CONFLICT (cell_id, valuation_time, label_source) DO UPDATE
                SET label = EXCLUDED.label,
                    -- Re-extraction refreshes static/insar but must NEVER
                    -- wipe the expensive CERRA rain enrichment (13 h of
                    -- archive replay) already attached to the row.
                    features = EXCLUDED.features ||
                        CASE WHEN training_samples.features ? 'rain'
                             THEN jsonb_build_object(
                                 'rain', training_samples.features->'rain')
                             ELSE '{}'::jsonb END,
                    split_block = EXCLUDED.split_block,
                    dataset_version_id = EXCLUDED.dataset_version_id
                """,
                it.cell_id,
                it.valuation_time,
                it.label,
                it.label_source,
                json.dumps(it.features, default=str),
                it.split_block,
                it.dataset_version_id,
            )
    log.info("training_samples.insert_many", count=len(rows))
    return len(rows)


async def count_samples() -> int:
    async with acquire() as conn:
        row = await conn.fetchrow("SELECT COUNT(*)::bigint AS n FROM training_samples")
    return int(row["n"]) if row else 0


async def list_blocks() -> list[str]:
    """Distinct ``split_block`` values, ordered — drives the CV iterator."""
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT split_block FROM training_samples ORDER BY split_block"
        )
    return [r["split_block"] for r in rows]


async def fetch_samples(*, blocks: list[str] | None = None) -> list[TrainingSample]:
    """Return samples, optionally filtered to one or more spatial blocks."""
    async with acquire() as conn:
        if blocks:
            rows = await conn.fetch(
                """
                SELECT cell_id, valuation_time, label, label_source,
                       features, split_block, dataset_version_id
                FROM training_samples
                WHERE split_block = ANY($1::text[])
                ORDER BY id
                """,
                blocks,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT cell_id, valuation_time, label, label_source,
                       features, split_block, dataset_version_id
                FROM training_samples
                ORDER BY id
                """
            )
    return [
        TrainingSample(
            cell_id=r["cell_id"],
            valuation_time=r["valuation_time"],
            label=int(r["label"]),
            label_source=r["label_source"],
            features=_coerce_features(r["features"]),
            split_block=r["split_block"],
            dataset_version_id=r["dataset_version_id"],
        )
        for r in rows
    ]


def _coerce_features(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        return dict(json.loads(raw))
    return {}


__all__ = [
    "LabelSource",
    "TrainingSample",
    "count_samples",
    "fetch_samples",
    "insert_many",
    "list_blocks",
]
