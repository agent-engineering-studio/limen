"""``limen geodata`` — nested CLI dispatcher for the Geo-Data Service.

Subcommands:
* ``list``           — print the manifest entries + dataset versions.
* ``init``           — download + import every enabled dataset.
* ``export-features``— populate ``cell_static_factors`` inputs in the operational DB.
* ``make-pmtiles``   — produce static-layer .pmtiles for the map.
* ``mcp``            — run the ``ispra-geo`` MCP server (FastMCP).

The actual implementations live in the ``geodata`` workspace package
and are imported lazily so the main ``limen`` CLI doesn't pull
pyogrio / fastmcp when the geodata profile isn't installed.
"""

from __future__ import annotations

import argparse
import sys


def _add_geodata_subcommands(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="geodata_command", required=True)

    list_parser = sub.add_parser(
        "list",
        help="print manifest entries + their import status",
    )
    list_parser.add_argument(
        "--manifest",
        default=None,
        help="override the manifest path (default: geodata/datasets.yaml)",
    )

    init_parser = sub.add_parser(
        "init",
        help="download + import every enabled dataset (idempotent)",
    )
    init_parser.add_argument("--manifest", default=None)
    init_parser.add_argument(
        "--only", default=None, help="comma-separated dataset names to process"
    )
    init_parser.add_argument("--region", default=None, help="restrict to a specific region tag")
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="re-import even when the checksum is unchanged",
    )
    init_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="plan-only: log what would be downloaded / imported",
    )

    export_parser = sub.add_parser(
        "export-features",
        help="upsert per-cell features into the operational DB",
    )
    export_parser.add_argument(
        "--to",
        required=True,
        help="operational DB DSN (postgresql://...) — separate from the geodata DB",
    )

    sub.add_parser("make-pmtiles", help="tippecanoe → static .pmtiles layers")

    mcp_parser = sub.add_parser("mcp", help="run the ispra-geo MCP server (FastMCP)")
    mcp_parser.add_argument(
        "--transport",
        default="stdio",
        choices=["stdio", "http"],
        help="MCP transport (default: stdio)",
    )


def build_subparser(top: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Hook called from ``limen.cli.main`` to attach the ``geodata`` group."""
    p = top.add_parser(
        "geodata",
        help="Geo-Data Service: ISPRA dataset ingestion + exports + MCP (§3.3.4-ter)",
    )
    _add_geodata_subcommands(p)


async def run(args: argparse.Namespace) -> int:
    """Dispatch the parsed namespace to the right geodata subcommand."""
    cmd = getattr(args, "geodata_command", None)
    if cmd == "list":
        from geodata.cli import run_list

        return await run_list(manifest_path=args.manifest)
    if cmd == "init":
        from geodata.cli import run_init

        return await run_init(
            manifest_path=args.manifest,
            only=args.only,
            region=args.region,
            force=args.force,
            dry_run=args.dry_run,
        )
    if cmd == "export-features":
        from geodata.cli import run_export_features

        return await run_export_features(operational_dsn=args.to)
    if cmd == "make-pmtiles":
        from geodata.cli import run_make_pmtiles

        return await run_make_pmtiles()
    if cmd == "mcp":
        from geodata.cli import run_mcp

        return await run_mcp(transport=args.transport)
    print(f"unknown geodata subcommand: {cmd!r}", file=sys.stderr)
    return 2
