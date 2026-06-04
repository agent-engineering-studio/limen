"""``ispra-geo`` MCP server entry point.

Thin FastMCP wrapper around :mod:`geodata.mcp.tools`. The tool bodies
all live in ``tools.py`` (testable without FastMCP installed); this
file only does the binding + transport.

Run via:

* ``limen geodata mcp --transport stdio``  (claude_desktop_config.json)
* ``limen geodata mcp --transport http``   (containerised)
"""

from __future__ import annotations

from typing import Any

import structlog

from geodata.db import connect
from geodata.mcp.tools import (
    RefreshAuthError,
    dataset_status,
    hazard_at,
    iffi_query,
    pai_summary,
    refresh,
)

_log: structlog.stdlib.BoundLogger = structlog.get_logger("geodata.mcp.server")

SERVER_NAME = "ispra-geo"
SERVER_INSTRUCTIONS = """ispra-geo — read-only ISPRA hazard tools (Limen Geo-Data Service).

Tools:
* hazard_at(lat, lon) → PAI class + authority + region at a point.
* iffi_query(bbox | region, movement_type?, limit) → IFFI landslides
  with attributes decoded via the Dizionari lookup tables.
* pai_summary(region | bbox) → per-class area / count distribution.
* dataset_status() → latest version + last refresh per manifest entry.
* refresh(dataset, admin_token) → trigger ingestion for one dataset
  (admin token via MCP_ADMIN_TOKEN environment variable).

All read tools are advisory: nothing here participates in Limen's
hourly scoring critical path.
"""


def _build_server() -> Any:
    """Construct the FastMCP server. Imports FastMCP lazily."""
    from fastmcp import FastMCP

    mcp = FastMCP(name=SERVER_NAME, instructions=SERVER_INSTRUCTIONS)

    @mcp.tool()
    async def tool_hazard_at(lat: float, lon: float) -> dict[str, Any]:
        """Return the PAI hazard class touching ``(lat, lon)``."""
        async with connect() as conn:
            return await hazard_at(conn, lat=lat, lon=lon)

    @mcp.tool()
    async def tool_iffi_query(
        bbox: tuple[float, float, float, float] | None = None,
        region: str | None = None,
        movement_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return IFFI landslides matching the filter (decoded attributes)."""
        async with connect() as conn:
            return await iffi_query(
                conn,
                bbox=bbox,
                region=region,
                movement_type=movement_type,
                limit=limit,
            )

    @mcp.tool()
    async def tool_pai_summary(
        region: str | None = None,
        bbox: tuple[float, float, float, float] | None = None,
    ) -> list[dict[str, Any]]:
        """Per-PAI-class area + feature count distribution."""
        async with connect() as conn:
            return await pai_summary(conn, region=region, bbox=bbox)

    @mcp.tool()
    async def tool_dataset_status() -> list[dict[str, Any]]:
        """Manifest entries with their last fetched version / checksum."""
        async with connect() as conn:
            return await dataset_status(conn)

    @mcp.tool()
    async def tool_refresh(dataset: str, admin_token: str) -> dict[str, Any]:
        """Re-run the ingestion pipeline for one dataset (admin only)."""
        try:
            return await refresh(dataset=dataset, admin_token=admin_token)
        except RefreshAuthError as exc:
            _log.warning("geodata.mcp.refresh_denied", reason=str(exc))
            return {"dataset": dataset, "error": "admin token missing or invalid"}

    return mcp


async def run_mcp_server(*, transport: str = "stdio") -> int:
    """Spin up FastMCP. ``stdio`` for Claude Desktop, ``http`` for the container."""
    try:
        mcp = _build_server()
    except ImportError as exc:
        _log.warning(
            "geodata.mcp.fastmcp_missing",
            error=str(exc),
            hint="install the `mcp` extra: uv pip install limen-geodata[mcp]",
        )
        return 1
    _log.info("geodata.mcp.starting", transport=transport, server=SERVER_NAME)
    if transport == "stdio":
        await mcp.run_async()
    elif transport == "http":
        await mcp.run_streamable_http_async(host="0.0.0.0", port=8765)
    else:
        _log.warning("geodata.mcp.unknown_transport", transport=transport)
        return 1
    return 0


__all__ = ["SERVER_INSTRUCTIONS", "SERVER_NAME", "run_mcp_server"]
