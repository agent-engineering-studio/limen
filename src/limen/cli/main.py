"""``limen`` console entry point — subcommand dispatcher.

Usage:
    limen migrate            Apply pending SQL migrations.
    limen seed               Apply migrations and seed Puglia/Basilicata AOIs + grids.
    limen bootstrap-static   Populate cell_static_factors (one-shot) for every seeded AOI.
    limen calibrate          Precompute s_static + per-AOI norm stats; run S vs ISPRA gate.
    limen backtest           Replay a historical window and emit a §2.5 metrics report.
    limen monitor-once       Run the MAF landslide workflow once for an AOI.
    limen forecast           Predictive run at now+H hours (forecast rain, no persistence).
    limen serve              Start the FastAPI HTTP server (uvicorn on :8080).
    limen train              Extract training samples and train the V2 ML model (MLflow).
    limen shadow-report      Champion vs ML-challenger comparison over the shadow window.
    limen report build       Generate the static HTML risk report once (idempotent).
    limen --help             Show this help.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Callable, Coroutine
from typing import Any

from limen import __version__
from limen.cli.backtest import run as _run_backtest
from limen.cli.bootstrap_static import run as _run_bootstrap_static
from limen.cli.calibrate import run as _run_calibrate
from limen.cli.forecast import run as _run_forecast
from limen.cli.geodata import build_subparser as _build_geodata_subparser
from limen.cli.geodata import run as _run_geodata
from limen.cli.geoserver_sync import run as _run_geoserver_sync
from limen.cli.ingest_events import run as _run_ingest_events
from limen.cli.ingest_kb import run as _run_ingest_kb
from limen.cli.mcp_serve import run as _run_mcp_serve
from limen.cli.migrate import run as _run_migrate
from limen.cli.monitor_once import run as _run_monitor_once
from limen.cli.report import run as _run_report_build
from limen.cli.seed import run as _run_seed
from limen.cli.server import run as _run_server
from limen.cli.shadow_report import run as _run_shadow_report
from limen.cli.sync_egms import run as _run_sync_egms
from limen.cli.train import run as _run_train
from limen.config.settings import get_settings
from limen.core.logging import configure_logging

Runner = Callable[[], Coroutine[Any, Any, int]]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="limen",
        description="Limen — landslide risk monitoring CLI",
    )
    parser.add_argument("--version", action="version", version=f"limen {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("migrate", help="apply pending SQL migrations")
    sub.add_parser("seed", help="apply migrations and seed AOIs + grids")
    sub.add_parser(
        "bootstrap-static",
        help="populate cell_static_factors (IFFI density, distance, PAI) for every seeded AOI",
    )
    sub.add_parser(
        "calibrate",
        help="precompute s_static + per-AOI norm stats; emit calibration report",
    )
    sub.add_parser(
        "backtest",
        help="replay a historical window and write a §2.5 metrics report",
    )
    sub.add_parser(
        "monitor-once",
        help="run the MAF workflow once (set LIMEN_MONITOR_AOI to target a single AOI)",
    )
    sub.add_parser(
        "forecast",
        help="predictive risk run at now+H hours (LIMEN_FORECAST_AOI / _HOURS / _CELL_LIMIT)",
    )
    sub.add_parser(
        "serve",
        help="start the FastAPI HTTP server (uvicorn on API__HOST:API__PORT, default :8080)",
    )
    sub.add_parser(
        "train",
        help="extract training samples and train the V2 ML model (LightGBM + MLflow)",
    )
    sub.add_parser(
        "shadow-report",
        help="champion vs ML-challenger comparison report (LIMEN_SHADOW_SINCE / _AOI)",
    )
    # ``limen report build`` — nested dispatcher for the static HTML risk
    # report. Only one action exists today, so this is a plain inline
    # subparser (not a `build_subparser`-style module like `geodata`, which
    # earns that indirection with five distinct subcommands).
    report_parser = sub.add_parser("report", help="static HTML risk report")
    report_sub = report_parser.add_subparsers(dest="report_command", required=True)
    report_sub.add_parser("build", help="generate the report once (idempotent)")
    sub.add_parser(
        "sync-egms",
        help="refresh cell_insar_features from Copernicus EGMS (V2.1)",
    )
    sub.add_parser(
        "geoserver-sync",
        help="load ISPRA IFFI + PAI from GeoServer PostGIS (GEOSERVER_SOURCE__DB_DSN)",
    )
    sub.add_parser(
        "ingest-events",
        help="load the ITALICA/e-ITALICA dated landslide catalogue (LIMEN_ITALICA_CSV)",
    )
    sub.add_parser(
        "mcp-serve",
        help="start the limen-ops MCP server (LIMEN_MCP_TRANSPORT=stdio|http)",
    )
    sub.add_parser(
        "ingest-kb",
        help="push the local corpus (papers + PAI + ISPRA + briefings) to the KG sidecar",
    )
    # ``limen geodata <subcommand>`` — nested dispatcher for the
    # Geo-Data Service (§3.3.4-ter). The implementation lives in the
    # `geodata` workspace package; imports are lazy so the geodata
    # optional deps stay out of the main CLI's runtime.
    _build_geodata_subparser(sub)
    return parser


def _load_dotenv() -> None:
    """Populate os.environ from .env for os.getenv-based knobs.

    pydantic-settings reads .env for the Settings model, but plain
    ``os.getenv`` calls (e.g. LIMEN_DEM_RASTER in the DEM/CORINE/geological
    sync jobs) do not. ``override=False`` keeps real env vars (Docker,
    shell) authoritative over the file.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover — python-dotenv ships with pydantic-settings
        return
    load_dotenv(override=False)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    _load_dotenv()
    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)

    runners: dict[str, Runner] = {
        "migrate": _run_migrate,
        "seed": _run_seed,
        "bootstrap-static": _run_bootstrap_static,
        "calibrate": _run_calibrate,
        "backtest": _run_backtest,
        "monitor-once": _run_monitor_once,
        "forecast": _run_forecast,
        "serve": _run_server,
        "train": _run_train,
        "shadow-report": _run_shadow_report,
        # only action is `build`; inspect args.report_command before adding a second.
        "report": _run_report_build,
        "sync-egms": _run_sync_egms,
        "ingest-kb": _run_ingest_kb,
        "geoserver-sync": _run_geoserver_sync,
        "ingest-events": _run_ingest_events,
        "mcp-serve": _run_mcp_serve,
    }
    if args.command == "geodata":
        try:
            return asyncio.run(_run_geodata(args))
        except KeyboardInterrupt:  # pragma: no cover
            return 130
    runner = runners[args.command]
    try:
        return asyncio.run(runner())
    except KeyboardInterrupt:  # pragma: no cover
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
