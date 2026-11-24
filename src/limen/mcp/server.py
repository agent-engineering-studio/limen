"""``limen-ops`` MCP server — Limen itself as agent tools.

Thin FastMCP wrapper around :mod:`limen.mcp.tools`; the tool bodies live
there (testable without FastMCP). Read tools are open; ``run_monitor`` is
gated by ``MCP_ADMIN_TOKEN`` (fail-closed). Designed to be registered in an
agent gateway (e.g. OpenClaw) next to ``idrogeo-mcp`` and ``geoserver-mcp``.

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
    comune_risk,
    hazards,
    landslide_zone_rain,
    multi_hazard_summary,
    national_report,
    radar_area_summary,
    radar_official_alert,
    radar_rain_ahead,
    radar_rain_at,
    radar_rarity,
    radar_status,
    radar_storm_now,
    rain_before_landslides,
    recent_alerts,
    risk_summary,
    run_forecast_history,
    run_monitor,
    top_comuni,
    top_risk_cells,
)

log = get_logger(__name__)

SERVER_NAME = "limen-ops"
SERVER_INSTRUCTIONS = """limen-ops — operational tools over the Limen landslide-risk system.

`hazard?` accepts landslide | flood | wildfire and defaults to landslide.
Call hazards() first to see which ones this deployment actually scores: a
valid name that is not enabled here returns an empty result, and an unknown
name returns an error naming the valid ones.

Read tools (open):
* risk_summary(aoi_id?, hazard?) → latest per-AOI assessment summary (cells
  per level, max score, when).
* top_risk_cells(limit?, aoi_id?, hazard?) → national ranking of the
  highest-risk cells from the latest assessments.
* cell_breakdown(cell_id, hazard?) → per-component breakdown (S/M/E/F/H/K) +
  the Italian briefing for one cell.
* recent_alerts(threshold?, since_hours?, limit?, hazard?) → cells at/above a
  level in the recent window.
* national_report(hazard?) → aggregated national picture (per-region
  summary, national top cells, ML shadow top, 24h alert counts) + a
  deterministic Italian rendering in `report_it`. `hazard` picks the leading
  one; `hazards` and `cascades` cover all of them regardless.
* multi_hazard_summary(cell_id? | aoi_id?) → one place, every hazard. Use
  this for "what is threatening here", not N calls to the per-hazard tools.
* landslide_zone_rain(cell_id | istat_code, hours?, until?) → rain measured by
  the regional gauges (Lombardy, Trentino) near a landslide zone — a cell, or
  the PAI/IFFI cells of a comune — with 1/3/6/24/72 h totals and the rain
  event against the Caine trigger threshold of its macroregion. Rain is
  never asked for a bare coordinate: always for a landslide zone. Outside
  the archived networks the answer is "non coperto", never zero; with
  unmeasured hours inside the event the ratio is a lower bound ("almeno").
  The archive is nightly: for the last hours use the radar tools.
* rain_before_landslides(cell_id | istat_code, since?, until?, hours_before?)
  → the zone's dated landslides (e-ITALICA, FraneItalia, fact check) and the
  gauge rain before each, against the same threshold. Cite the gauge's
  `attribuzione` (Meteotrentino is CC BY 4.0).
* top_comuni(limit?, aoi_id?) e comune_risk(istat_code) → rollup per comune,
  su tutti i pericoli (migrazione 051).
  **Landslide only**: the rollup view is pinned to it, so passing another
  hazard returns an error rather than mislabelled numbers.

Admin tools (MCP_ADMIN_TOKEN, fail-closed):
* run_monitor(aoi_id, admin_token, cell_limit?, hazard?) → run the full
  monitoring workflow once for an AOI.
* build_report(admin_token) → generate the static HTML risk report once
  (idempotent). Recurring builds already run via APScheduler. Landslide only.
* forecast_history(admin_token, aoi_ids?, hazard?) → persist the per-cell
  forecast trend (+24/48/72h) used by the sidebar / report charts.

Events (experimental, MCP__EVENTI=true; poll only): events/list and
events/poll serve limen.alert.dispatched, limen.risk.class_changed and
limen.source.unmeasured, each a Limen estimate and never an official warning.

With idrogeo-mcp (ISPRA IdroGEO data, registered next to this server):
* cite the `source` field of each idrogeo-mcp answer as it is, not a generic
  "ISPRA": IFFI and events are CC BY-SA 4.0, the risk indicators CC BY 4.0;
* before giving an answer with IdroGEO numbers, call idrogeo-mcp
  `check_answer` with your draft and the tool results, and fix any number it
  lists (it checks that a number exists in the data, not that it is said of
  the right thing);
* when you talk about a municipality's landslides, call `data_reliability`
  (or read `affidabilita_iffi` from comune_risk) and say its limits: few
  mapped landslides where IFFI is poorly surveyed do not mean safe ground.

Scores come from the deterministic/ML engine and are never altered here:
these tools read and trigger, they do not decide.
"""


def _build_server() -> Any:
    from fastmcp import FastMCP

    mcp = FastMCP(name=SERVER_NAME, instructions=SERVER_INSTRUCTIONS)

    @mcp.tool()
    async def tool_radar_rain_at(lon: float, lat: float, hours: int = 1) -> dict[str, Any]:
        """DPC radar: rain of the last 1/3/6/12/24 h at a point (mm), with its frame
        and how far the radar can be trusted there. {} = not measured, not dry."""
        return await radar_rain_at(lon, lat, hours)

    @mcp.tool()
    async def tool_radar_area_summary(
        west: float, south: float, east: float, north: float, hours: int = 1
    ) -> dict[str, Any]:
        """DPC radar: rain over a lon/lat box — max, mean, km² over thresholds."""
        return await radar_area_summary(west, south, east, north, hours)

    @mcp.tool()
    async def tool_radar_storm_now(
        west: float | None = None,
        south: float | None = None,
        east: float | None = None,
        north: float | None = None,
    ) -> dict[str, Any]:
        """DPC radar: storms (≥ 10 mm/h) on the newest frame and where they move."""
        return await radar_storm_now(west, south, east, north)

    @mcp.tool()
    async def tool_radar_rain_ahead(
        lon: float, lat: float, minutes: int = 60, mm: float = 20.0
    ) -> dict[str, Any]:
        """DPC radar NOWCAST (a forecast, 5-120 min): rain ahead at a point and the
        chance of at least `mm`. Good on where the rain goes, poor on peaks."""
        return await radar_rain_ahead(lon, lat, minutes, mm)

    @mcp.tool()
    async def tool_radar_official_alert(
        lon: float | None = None, lat: float | None = None, place: str | None = None
    ) -> dict[str, Any]:
        """The official DPC criticality bulletin level, today and tomorrow."""
        return await radar_official_alert(lon, lat, place)

    @mcp.tool()
    async def tool_radar_rarity(lon: float, lat: float, hours: int, mm: float) -> dict[str, Any]:
        """How rare `mm` of rain in 1/3/6/24 h is at a place (return period, years)."""
        return radar_rarity(lon, lat, hours, mm)

    @mcp.tool()
    async def tool_radar_status(
        lon: float | None = None, lat: float | None = None
    ) -> dict[str, Any]:
        """Which DPC radars are reported on/off (a hint, not proof)."""
        return await radar_status(lon, lat)

    @mcp.tool()
    async def tool_landslide_zone_rain(
        cell_id: str | None = None,
        istat_code: str | None = None,
        hours: int = 72,
        until: str | None = None,
    ) -> dict[str, Any]:
        """Gauge rain near a landslide zone (cell or comune) against the trigger threshold."""
        return await landslide_zone_rain(cell_id, istat_code, hours, until)

    @mcp.tool()
    async def tool_rain_before_landslides(
        cell_id: str | None = None,
        istat_code: str | None = None,
        since: str = "2009-01-01",
        until: str | None = None,
        hours_before: int = 72,
    ) -> dict[str, Any]:
        """A zone's dated landslides and the gauge rain in the hours before each."""
        return await rain_before_landslides(cell_id, istat_code, since, until, hours_before)

    @mcp.tool()
    async def tool_risk_summary(
        aoi_id: str | None = None, hazard: str | None = None
    ) -> list[dict[str, Any]]:
        """Latest assessment summary per AOI (all AOIs when omitted)."""
        return await risk_summary(aoi_id, hazard)

    @mcp.tool()
    async def tool_top_risk_cells(
        limit: int = 10, aoi_id: str | None = None, hazard: str | None = None
    ) -> list[dict[str, Any]]:
        """Highest-risk cells from the latest assessments (national ranking)."""
        return await top_risk_cells(limit=limit, aoi_id=aoi_id, hazard=hazard)

    @mcp.tool()
    async def tool_cell_breakdown(cell_id: str, hazard: str | None = None) -> dict[str, Any]:
        """Per-component breakdown + Italian briefing for one cell."""
        return await cell_breakdown(cell_id, hazard)

    @mcp.tool()
    async def tool_recent_alerts(
        threshold: str = "Moderate",
        since_hours: int = 24,
        limit: int = 50,
        hazard: str | None = None,
    ) -> list[dict[str, Any]]:
        """Cells at/above a risk level in the recent window."""
        return await recent_alerts(
            threshold=threshold, since_hours=since_hours, limit=limit, hazard=hazard
        )

    @mcp.tool()
    async def tool_hazards() -> dict[str, Any]:
        """Hazards this deployment can score. Call before passing `hazard`."""
        return await hazards()

    @mcp.tool()
    async def tool_national_report(hazard: str | None = None) -> dict[str, Any]:
        """Aggregated national picture + Italian rendering (report_it)."""
        return await national_report(hazard)

    @mcp.tool()
    async def tool_multi_hazard_summary(
        cell_id: str | None = None, aoi_id: str | None = None
    ) -> dict[str, Any]:
        """Cross-hazard picture for one cell or one AOI. Give exactly one."""
        return await multi_hazard_summary(cell_id=cell_id, aoi_id=aoi_id)

    @mcp.tool()
    async def tool_comune_risk(istat_code: str) -> dict[str, Any]:
        """Rollup di un comune su tutti i pericoli: peggiore, conteggi, esposizione."""
        return await comune_risk(istat_code)

    @mcp.tool()
    async def tool_top_comuni(limit: int = 10, aoi_id: str | None = None) -> list[dict[str, Any]]:
        """Comuni ordinati dal peggiore fra tutti i pericoli."""
        return await top_comuni(limit=limit, aoi_id=aoi_id)

    @mcp.tool()
    async def tool_run_monitor(
        aoi_id: str,
        admin_token: str,
        cell_limit: int | None = None,
        hazard: str | None = None,
    ) -> dict[str, Any]:
        """Run the monitoring workflow once for an AOI (admin only)."""
        try:
            return await run_monitor(
                aoi_id, admin_token=admin_token, cell_limit=cell_limit, hazard=hazard
            )
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
        admin_token: str,
        aoi_ids: list[str] | None = None,
        hazard: str | None = None,
    ) -> dict[str, Any]:
        """Persist the per-cell forecast trend for the UI charts (admin only)."""
        try:
            return await run_forecast_history(
                admin_token=admin_token, aoi_ids=aoi_ids, hazard=hazard
            )
        except AdminAuthError as exc:
            log.warning("limen.mcp.forecast_history_denied", reason=str(exc))
            return {"error": str(exc)}

    from limen.config.settings import get_settings

    if get_settings().mcp.eventi:
        from limen.mcp.eventi import EventiLimen

        mcp.add_extension(EventiLimen())
        log.info("limen.mcp.eventi", identificatore=EventiLimen.identifier)
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
