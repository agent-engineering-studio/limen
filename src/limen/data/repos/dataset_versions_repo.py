"""Dataset-versions registry.

Every external dataset ingested into Limen records a row here so we can
answer "which version of dataset X did risk assessment Y use?". The
``version`` field is typically a content hash (idempotency guard for
sync jobs) but may be any source-provided revision label.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from limen.data.db import acquire


@dataclass(frozen=True, slots=True)
class DatasetVersion:
    id: int
    source: str
    dataset: str
    version: str
    fetched_at: datetime
    valid_from: datetime | None
    valid_to: datetime | None
    metadata: dict[str, Any]


def content_hash(items: list[bytes] | list[str] | bytes) -> str:
    """Compute a stable hash of source bytes/strings for version tagging."""
    h = hashlib.sha256()
    if isinstance(items, bytes):
        h.update(items)
        return h.hexdigest()
    for it in items:
        h.update(it if isinstance(it, bytes) else it.encode("utf-8"))
    return h.hexdigest()


async def find(source: str, dataset: str, version: str) -> DatasetVersion | None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, source, dataset, version, fetched_at, valid_from, valid_to, metadata
            FROM dataset_versions
            WHERE source = $1 AND dataset = $2 AND version = $3
            """,
            source,
            dataset,
            version,
        )
    if row is None:
        return None
    meta = row["metadata"]
    if isinstance(meta, str):
        meta = json.loads(meta)
    return DatasetVersion(
        id=int(row["id"]),
        source=row["source"],
        dataset=row["dataset"],
        version=row["version"],
        fetched_at=row["fetched_at"],
        valid_from=row["valid_from"],
        valid_to=row["valid_to"],
        metadata=meta or {},
    )


async def record(
    *,
    source: str,
    dataset: str,
    version: str,
    metadata: dict[str, Any] | None = None,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
) -> int:
    """Insert (or return the existing id) for a ``(source, dataset, version)`` triple."""
    meta_json = json.dumps(metadata or {}, default=str)
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO dataset_versions (source, dataset, version, valid_from, valid_to, metadata)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb)
            ON CONFLICT (source, dataset, version) DO UPDATE
            SET metadata = EXCLUDED.metadata
            RETURNING id
            """,
            source,
            dataset,
            version,
            valid_from,
            valid_to,
            meta_json,
        )
    assert row is not None
    return int(row["id"])
