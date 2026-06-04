"""asyncpg connection helpers for the Geo-Data Service DB.

The geodata service uses its OWN PostgreSQL instance (per
§3.3.4-ter) — different host, different volume, different DSN from
the operational DB. This module is intentionally tiny; nothing here
imports from ``limen.*``.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
import structlog

_log: structlog.stdlib.BoundLogger = structlog.get_logger("geodata.db")


GEODATA_DSN_ENV = "GEODATA_DB_DSN"


def get_dsn() -> str:
    """Read ``GEODATA_DB_DSN`` from the environment, or fall back to dev."""
    return os.environ.get(
        GEODATA_DSN_ENV,
        "postgresql://geodata:geodata@localhost:55432/geodata",
    )


@asynccontextmanager
async def connect(dsn: str | None = None) -> AsyncIterator[asyncpg.Connection]:
    """One short-lived connection. Suitable for the one-shot init job."""
    target = dsn or get_dsn()
    conn = await asyncpg.connect(target)
    try:
        yield conn
    finally:
        await conn.close()


SCHEMA_DDL = """
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS dataset_versions (
    id          bigserial PRIMARY KEY,
    name        text NOT NULL,
    url         text NOT NULL,
    checksum    text NOT NULL,
    etag        text,
    fetched_at  timestamptz NOT NULL DEFAULT now(),
    row_count   bigint,
    metadata    jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (name, checksum)
);
CREATE INDEX IF NOT EXISTS dataset_versions_name_idx
    ON dataset_versions (name, fetched_at DESC);

-- pai_landslide_hazard — national PAI mosaic (~930k polygons).
CREATE TABLE IF NOT EXISTS pai_landslide_hazard (
    pai_id        text PRIMARY KEY,
    hazard_class  text NOT NULL,
    authority     text,
    region        text,
    geom          geometry(MultiPolygon, 4326) NOT NULL,
    attributes    jsonb NOT NULL DEFAULT '{}'::jsonb,
    dataset_version_id bigint REFERENCES dataset_versions(id) ON DELETE SET NULL,
    updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS pai_landslide_hazard_class_idx
    ON pai_landslide_hazard (hazard_class);
CREATE INDEX IF NOT EXISTS pai_landslide_hazard_geom_gix
    ON pai_landslide_hazard USING GIST (geom);

-- iffi_landslides — per-region IFFI inventory (multiple geometry layers
-- unified by the `geom_type` column: 'piff_line' | 'piff_poly' |
-- 'aree_poly' | 'dgpv_poly'). The id is composite (region + raw IFFI id
-- + geom_type) so the same IFFI feature in two layers doesn't collide.
CREATE TABLE IF NOT EXISTS iffi_landslides (
    id              text PRIMARY KEY,
    iffi_id         text,
    region          text NOT NULL,
    geom_type       text NOT NULL,
    movement_type   text,
    state           text,
    velocity_class  text,
    occurrence_date date,
    geom            geometry(Geometry, 4326) NOT NULL,
    attributes      jsonb NOT NULL DEFAULT '{}'::jsonb,
    dataset_version_id bigint REFERENCES dataset_versions(id) ON DELETE SET NULL,
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS iffi_landslides_region_idx
    ON iffi_landslides (region);
CREATE INDEX IF NOT EXISTS iffi_landslides_movement_idx
    ON iffi_landslides (movement_type);
CREATE INDEX IF NOT EXISTS iffi_landslides_geom_gix
    ON iffi_landslides USING GIST (geom);

-- idraulica_hazard — flood mosaic (out of V1 landslide scope; imported
-- but unused. Same shape as PAI so the future flood module can mirror
-- the codebase.)
CREATE TABLE IF NOT EXISTS idraulica_hazard (
    pai_id        text PRIMARY KEY,
    hazard_class  text NOT NULL,
    authority     text,
    region        text,
    geom          geometry(MultiPolygon, 4326) NOT NULL,
    attributes    jsonb NOT NULL DEFAULT '{}'::jsonb,
    dataset_version_id bigint REFERENCES dataset_versions(id) ON DELETE SET NULL,
    updated_at    timestamptz NOT NULL DEFAULT now()
);

-- IFFI Dizionari — code → human-readable label.
CREATE TABLE IF NOT EXISTS iffi_lookup_causes (
    code   text PRIMARY KEY,
    label  text NOT NULL
);
CREATE TABLE IF NOT EXISTS iffi_lookup_movements (
    code   text PRIMARY KEY,
    label  text NOT NULL
);
CREATE TABLE IF NOT EXISTS iffi_lookup_lithology (
    code   text PRIMARY KEY,
    label  text NOT NULL
);
"""


async def ensure_schema(conn: asyncpg.Connection) -> None:
    """Idempotent DDL — runs each time the init job starts."""
    await conn.execute(SCHEMA_DDL)
    _log.debug("geodata.db.schema_ready")


async def get_existing_checksum(conn: asyncpg.Connection, *, name: str) -> str | None:
    """Return the most recent checksum recorded for ``name`` (or None)."""
    row = await conn.fetchrow(
        """
        SELECT checksum FROM dataset_versions
        WHERE name = $1
        ORDER BY fetched_at DESC
        LIMIT 1
        """,
        name,
    )
    return row["checksum"] if row else None


async def insert_dataset_version(
    conn: asyncpg.Connection,
    *,
    name: str,
    url: str,
    checksum: str,
    etag: str | None,
    row_count: int,
    metadata: dict[str, Any] | None = None,
) -> int:
    """Record a successful import."""
    import json

    payload = json.dumps(metadata or {}, default=str)
    row = await conn.fetchrow(
        """
        INSERT INTO dataset_versions (name, url, checksum, etag, row_count, metadata)
        VALUES ($1, $2, $3, $4, $5, $6::jsonb)
        ON CONFLICT (name, checksum) DO UPDATE
        SET fetched_at = now(),
            etag       = EXCLUDED.etag,
            row_count  = EXCLUDED.row_count,
            metadata   = EXCLUDED.metadata
        RETURNING id
        """,
        name,
        url,
        checksum,
        etag,
        row_count,
        payload,
    )
    if row is None:  # pragma: no cover — RETURNING always populates on success
        raise RuntimeError("dataset_versions insert did not return an id")
    return int(row["id"])


__all__ = [
    "GEODATA_DSN_ENV",
    "SCHEMA_DDL",
    "connect",
    "ensure_schema",
    "get_dsn",
    "get_existing_checksum",
    "insert_dataset_version",
]
