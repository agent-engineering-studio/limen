"""``limen`` console entry point — subcommand dispatcher.

Usage:
    limen migrate           Apply pending SQL migrations.
    limen seed              Apply migrations and seed Puglia/Basilicata AOIs + grids.
    limen bootstrap-static  Populate cell_static_factors (one-shot) for every seeded AOI.
    limen --help            Show this help.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Callable, Coroutine
from typing import Any

from limen import __version__
from limen.cli.bootstrap_static import run as _run_bootstrap_static
from limen.cli.migrate import run as _run_migrate
from limen.cli.seed import run as _run_seed
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)

    runners: dict[str, Runner] = {
        "migrate": _run_migrate,
        "seed": _run_seed,
        "bootstrap-static": _run_bootstrap_static,
    }
    runner = runners[args.command]
    try:
        return asyncio.run(runner())
    except KeyboardInterrupt:  # pragma: no cover
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
