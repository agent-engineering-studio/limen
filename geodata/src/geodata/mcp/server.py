"""MCP server entry point — Stage D placeholder."""

from __future__ import annotations

import structlog

_log: structlog.stdlib.BoundLogger = structlog.get_logger("geodata.mcp")


async def run_mcp_server(*, transport: str = "stdio") -> int:
    _log.warning(
        "geodata.mcp.not_implemented_yet",
        transport=transport,
        hint="ispra-geo MCP server lands in Stage D",
    )
    return 1
