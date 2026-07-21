"""``limen-ops`` MCP server — Limen itself as agent tools.

Thin FastMCP wrapper around :mod:`limen.mcp.tools`; the tool bodies live
there (testable without FastMCP). Read tools are open; ``run_monitor`` is
gated by ``MCP_ADMIN_TOKEN`` (fail-closed). Designed to be registered in an
agent gateway (e.g. OpenClaw) next to ``ispra-geo`` and ``geoserver-mcp``.

Run via ``limen mcp-serve`` (stdio, default) or
``limen mcp-serve --transport http`` (streamable HTTP on :8766).
"""

from __future__ import annotations

import os
from typing import Any

from limen.core.logging import get_logger
from limen.data.db import lifespan_pool
from limen.mcp.tools import (
    AdminAuthError,
    build_static_report,
    cell_breakdown,
    national_report,
    recent_alerts,
    risk_summary,
    run_forecast_history,
    run_monitor,
    top_risk_cells,
)

log = get_logger(__name__)

SERVER_NAME = "limen-ops"
SERVER_INSTRUCTIONS = """limen-ops — operational tools over the Limen landslide-risk system.

Read tools (open):
* risk_summary(aoi_id?) → latest per-AOI assessment summary (cells per
  level, max score, when).
* top_risk_cells(limit?, aoi_id?) → national ranking of the highest-risk
  cells from the latest assessments.
* cell_breakdown(cell_id) → per-component breakdown (S/M/E/F/H/K) + the
  Italian briefing for one cell.
* recent_alerts(threshold?, since_hours?, limit?) → cells at/above a level
  in the recent window.
* national_report() → aggregated national picture (per-region summary,
  national top cells, ML shadow top, 24h alert counts) + a deterministic
  Italian rendering in `report_it`.

Admin tools (MCP_ADMIN_TOKEN, fail-closed):
* run_monitor(aoi_id, admin_token, cell_limit?) → run the full monitoring
  workflow once for an AOI.
* build_report(admin_token) → generate the static HTML risk report once
  (idempotent). Recurring builds already run via APScheduler.
* forecast_history(admin_token, aoi_ids?) → persist the per-cell forecast
  trend (+24/48/72h) used by the sidebar / report charts.

Scores come from the deterministic/ML engine and are never altered here:
these tools read and trigger, they do not decide.
"""


def _build_server() -> Any:
    from fastmcp import FastMCP

    mcp = FastMCP(name=SERVER_NAME, instructions=SERVER_INSTRUCTIONS)

    @mcp.tool()
    async def tool_risk_summary(aoi_id: str | None = None) -> list[dict[str, Any]]:
        """Latest assessment summary per AOI (all AOIs when omitted)."""
        return await risk_summary(aoi_id)

    @mcp.tool()
    async def tool_top_risk_cells(
        limit: int = 10, aoi_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Highest-risk cells from the latest assessments (national ranking)."""
        return await top_risk_cells(limit=limit, aoi_id=aoi_id)

    @mcp.tool()
    async def tool_cell_breakdown(cell_id: str) -> dict[str, Any]:
        """Per-component breakdown + Italian briefing for one cell."""
        return await cell_breakdown(cell_id)

    @mcp.tool()
    async def tool_recent_alerts(
        threshold: str = "Moderate", since_hours: int = 24, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Cells at/above a risk level in the recent window."""
        return await recent_alerts(threshold=threshold, since_hours=since_hours, limit=limit)

    @mcp.tool()
    async def tool_national_report() -> dict[str, Any]:
        """Aggregated national picture + Italian rendering (report_it)."""
        return await national_report()

    @mcp.tool()
    async def tool_run_monitor(
        aoi_id: str, admin_token: str, cell_limit: int | None = None
    ) -> dict[str, Any]:
        """Run the monitoring workflow once for an AOI (admin only)."""
        try:
            return await run_monitor(aoi_id, admin_token=admin_token, cell_limit=cell_limit)
        except AdminAuthError as exc:
            log.warning("limen.mcp.run_monitor_denied", reason=str(exc))
            return {"aoi_id": aoi_id, "error": str(exc)}

    @mcp.tool()
    async def tool_build_report(admin_token: str) -> dict[str, Any]:
        """Generate the static HTML risk report once, on demand (admin only)."""
        try:
            return await build_static_report(admin_token=admin_token)
        except AdminAuthError as exc:
            log.warning("limen.mcp.build_report_denied", reason=str(exc))
            return {"error": str(exc)}

    @mcp.tool()
    async def tool_forecast_history(
        admin_token: str, aoi_ids: list[str] | None = None
    ) -> dict[str, Any]:
        """Persist the per-cell forecast trend for the UI charts (admin only)."""
        try:
            return await run_forecast_history(admin_token=admin_token, aoi_ids=aoi_ids)
        except AdminAuthError as exc:
            log.warning("limen.mcp.forecast_history_denied", reason=str(exc))
            return {"error": str(exc)}

    return mcp


async def run_mcp_server(*, transport: str = "stdio") -> int:
    """Start FastMCP with the shared asyncpg pool for the process lifetime."""
    try:
        mcp = _build_server()
    except ImportError as exc:
        log.warning("limen.mcp.fastmcp_missing", error=str(exc))
        return 1
    log.info("limen.mcp.starting", transport=transport, server=SERVER_NAME)
    async with lifespan_pool():
        if transport == "stdio":
            await mcp.run_async()
        elif transport == "http":
            host = os.getenv("LIMEN_MCP_HTTP_HOST", "0.0.0.0")
            port = int(os.getenv("LIMEN_MCP_HTTP_PORT", "8766"))
            await mcp.run_http_async(host=host, port=port)
        else:
            log.error("limen.mcp.bad_transport", transport=transport)
            return 2
    return 0
