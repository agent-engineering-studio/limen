"""Pure tool implementations for the ``ispra-geo`` MCP server.

These are async functions that take typed inputs + an
:class:`asyncpg.Connection` and return JSON-able dictionaries — no
FastMCP dependency here, so the logic is unit-testable in isolation.

The MCP server wrapper (:mod:`geodata.mcp.server`) thinly binds these
functions to FastMCP tool decorators.

Every tool is read-only; the one exception, :func:`refresh`, requires
an admin bearer token and triggers the init pipeline for a single
dataset.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import asyncpg
import structlog

_log: structlog.stdlib.BoundLogger = structlog.get_logger("geodata.mcp.tools")


# Output schema —----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HazardAtResult:
    lat: float
    lon: float
    pai_class: str | None
    pai_authority: str | None
    region: str | None


@dataclass(frozen=True, slots=True)
class IffiFeature:
    id: str
    iffi_id: str | None
    region: str
    geom_type: str
    movement_type: str | None
    movement_label: str | None
    state: str | None
    velocity_class: str | None
    occurrence_date: str | None


@dataclass(frozen=True, slots=True)
class PaiSummaryRow:
    hazard_class: str
    feature_count: int
    area_km2: float


@dataclass(frozen=True, slots=True)
class DatasetStatusRow:
    name: str
    url: str
    last_fetched_at: str | None
    checksum: str | None
    row_count: int | None


# Tools — hazard_at ----------------------------------------------------------


async def hazard_at(conn: asyncpg.Connection, *, lat: float, lon: float) -> dict[str, Any]:
    """Return the PAI class at ``(lat, lon)`` (most severe if multiple)."""
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        raise ValueError(f"lat/lon out of range: ({lat}, {lon})")
    row = await conn.fetchrow(
        """
        WITH pt AS (
            SELECT ST_SetSRID(ST_MakePoint($1, $2), 4326) AS geom
        )
        SELECT p.hazard_class, p.authority, p.region
        FROM pai_landslide_hazard p, pt
        WHERE ST_Intersects(p.geom, pt.geom)
        ORDER BY CASE p.hazard_class
            WHEN 'P4' THEN 5
            WHEN 'P3' THEN 4
            WHEN 'P2' THEN 3
            WHEN 'P1' THEN 2
            WHEN 'AA' THEN 1
            ELSE 0
        END DESC
        LIMIT 1
        """,
        lon,
        lat,
    )
    return {
        "lat": lat,
        "lon": lon,
        "pai_class": row["hazard_class"] if row else None,
        "pai_authority": row["authority"] if row else None,
        "region": row["region"] if row else None,
    }


# Tools — iffi_query ---------------------------------------------------------


async def iffi_query(
    conn: asyncpg.Connection,
    *,
    bbox: tuple[float, float, float, float] | None = None,
    region: str | None = None,
    movement_type: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Filtered IFFI landslides with attributes decoded via ``iffi_lookup_*``.

    Exactly one of ``bbox`` / ``region`` is required; ``movement_type``
    narrows further. ``limit`` is hard-capped at 500.
    """
    if limit <= 0 or limit > 500:
        raise ValueError(f"limit must be in [1, 500]: {limit}")
    if bbox is None and region is None:
        raise ValueError("one of bbox or region is required")

    clauses: list[str] = []
    params: list[Any] = []

    if bbox is not None:
        min_lon, min_lat, max_lon, max_lat = bbox
        clauses.append("ST_Intersects(i.geom, ST_MakeEnvelope($1, $2, $3, $4, 4326))")
        params.extend([min_lon, min_lat, max_lon, max_lat])
    if region is not None:
        params.append(region.strip().lower())
        clauses.append(f"i.region = ${len(params)}")
    if movement_type is not None:
        params.append(movement_type)
        clauses.append(f"i.movement_type = ${len(params)}")

    params.append(limit)
    sql = f"""
        SELECT
            i.id, i.iffi_id, i.region, i.geom_type,
            i.movement_type,
            m.label AS movement_label,
            i.state,
            i.velocity_class,
            i.occurrence_date
        FROM iffi_landslides i
        LEFT JOIN iffi_lookup_movements m ON m.code = i.movement_type
        WHERE {" AND ".join(clauses)}
        ORDER BY i.id
        LIMIT ${len(params)}
        """
    rows = await conn.fetch(sql, *params)
    return [
        {
            "id": str(r["id"]),
            "iffi_id": r["iffi_id"],
            "region": r["region"],
            "geom_type": r["geom_type"],
            "movement_type": r["movement_type"],
            "movement_label": r["movement_label"],
            "state": r["state"],
            "velocity_class": r["velocity_class"],
            "occurrence_date": (r["occurrence_date"].isoformat() if r["occurrence_date"] else None),
        }
        for r in rows
    ]


# Tools — pai_summary --------------------------------------------------------


async def pai_summary(
    conn: asyncpg.Connection,
    *,
    region: str | None = None,
    bbox: tuple[float, float, float, float] | None = None,
) -> list[dict[str, Any]]:
    """Per-class area / count distribution for the PAI mosaic.

    Areas come from ``ST_Area`` over the geography type so they're
    reported in km² regardless of latitude.
    """
    clauses: list[str] = []
    params: list[Any] = []
    if region is not None:
        params.append(region.strip().lower())
        clauses.append(f"p.region = ${len(params)}")
    if bbox is not None:
        min_lon, min_lat, max_lon, max_lat = bbox
        params.extend([min_lon, min_lat, max_lon, max_lat])
        idx = len(params)
        clauses.append(
            "ST_Intersects(p.geom, "
            f"ST_MakeEnvelope(${idx - 3}, ${idx - 2}, ${idx - 1}, ${idx}, 4326))"
        )
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""
        SELECT
            p.hazard_class,
            COUNT(*) AS feature_count,
            COALESCE(SUM(ST_Area(p.geom::geography)), 0.0) / 1.0e6 AS area_km2
        FROM pai_landslide_hazard p
        {where}
        GROUP BY p.hazard_class
        ORDER BY p.hazard_class
        """
    rows = await conn.fetch(sql, *params)
    return [
        {
            "hazard_class": r["hazard_class"],
            "feature_count": int(r["feature_count"]),
            "area_km2": float(r["area_km2"]),
        }
        for r in rows
    ]


# Tools — dataset_status -----------------------------------------------------


async def dataset_status(conn: asyncpg.Connection) -> list[dict[str, Any]]:
    """Latest dataset_versions row per dataset name."""
    rows = await conn.fetch(
        """
        SELECT DISTINCT ON (name)
            name, url, fetched_at, checksum, row_count
        FROM dataset_versions
        ORDER BY name, fetched_at DESC
        """
    )
    return [
        {
            "name": r["name"],
            "url": r["url"],
            "last_fetched_at": r["fetched_at"].isoformat() if r["fetched_at"] else None,
            "checksum": r["checksum"],
            "row_count": int(r["row_count"]) if r["row_count"] is not None else None,
        }
        for r in rows
    ]


# Tools — refresh ------------------------------------------------------------


MCP_ADMIN_TOKEN_ENV = "MCP_ADMIN_TOKEN"


class RefreshAuthError(PermissionError):
    """Raised when the caller does not present the admin token."""


def _admin_token_matches(provided: str | None) -> bool:
    expected = os.environ.get(MCP_ADMIN_TOKEN_ENV)
    if not expected:
        # No token configured → refresh is disabled. Refusing is the
        # safer default than silently allowing.
        return False
    return provided is not None and provided == expected


async def refresh(*, dataset: str, admin_token: str | None) -> dict[str, Any]:
    """Trigger the init pipeline for a single dataset (admin only)."""
    if not _admin_token_matches(admin_token):
        raise RefreshAuthError("admin token missing or invalid")
    # Lazy-imported so the MCP module stays importable even when the
    # init deps aren't present (the container always installs both).
    from pathlib import Path

    from geodata.init.runner import run_init_pipeline

    manifest_path = Path(__file__).resolve().parents[1] / "datasets.yaml"
    rc = await run_init_pipeline(
        manifest_path=manifest_path,
        only=dataset,
        force=True,
    )
    return {"dataset": dataset, "exit_code": rc}


__all__ = [
    "MCP_ADMIN_TOKEN_ENV",
    "DatasetStatusRow",
    "HazardAtResult",
    "IffiFeature",
    "PaiSummaryRow",
    "RefreshAuthError",
    "dataset_status",
    "hazard_at",
    "iffi_query",
    "pai_summary",
    "refresh",
]
