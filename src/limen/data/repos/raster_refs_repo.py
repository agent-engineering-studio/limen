"""Raster references repository.

The DB holds only metadata + bbox + checksum; the actual raster bytes
live in the :class:`ObjectStore`. Both `seismic_events.raster_ref_id` and
`fire_perimeters.raster_ref_id` point here.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from shapely.geometry import Polygon

from limen.data.db import acquire


@dataclass(frozen=True, slots=True)
class RasterRef:
    id: int
    kind: str
    bucket: str | None
    prefix: str | None
    path: str
    bbox: Polygon
    crs: str
    checksum_sha256: str | None
    size_bytes: int | None
    metadata: dict[str, Any]
    dataset_version_id: int | None


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def upsert(
    *,
    kind: str,
    path: str,
    bbox: Polygon,
    crs: str,
    bucket: str | None = None,
    prefix: str | None = None,
    checksum_sha256: str | None = None,
    size_bytes: int | None = None,
    metadata: dict[str, Any] | None = None,
    dataset_version_id: int | None = None,
) -> int:
    """Insert (or update by (kind, path)) a raster reference and return its id."""
    meta_json = json.dumps(metadata or {}, default=str)
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO raster_refs (
                kind, bucket, prefix, path, bbox, crs, checksum_sha256,
                size_bytes, metadata, dataset_version_id
            ) VALUES (
                $1, $2, $3, $4, ST_SetSRID($5::geometry, 4326), $6, $7, $8, $9::jsonb, $10
            )
            ON CONFLICT (kind, path) DO UPDATE
            SET bucket             = EXCLUDED.bucket,
                prefix             = EXCLUDED.prefix,
                bbox               = EXCLUDED.bbox,
                crs                = EXCLUDED.crs,
                checksum_sha256    = EXCLUDED.checksum_sha256,
                size_bytes         = EXCLUDED.size_bytes,
                metadata           = EXCLUDED.metadata,
                dataset_version_id = COALESCE(EXCLUDED.dataset_version_id,
                                              raster_refs.dataset_version_id)
            RETURNING id
            """,
            kind,
            bucket,
            prefix,
            path,
            bbox,
            crs,
            checksum_sha256,
            size_bytes,
            meta_json,
            dataset_version_id,
        )
    assert row is not None
    return int(row["id"])


async def count(kind: str | None = None) -> int:
    async with acquire() as conn:
        if kind is None:
            row = await conn.fetchrow("SELECT COUNT(*)::bigint AS n FROM raster_refs")
        else:
            row = await conn.fetchrow(
                "SELECT COUNT(*)::bigint AS n FROM raster_refs WHERE kind = $1", kind
            )
    return int(row["n"]) if row else 0
