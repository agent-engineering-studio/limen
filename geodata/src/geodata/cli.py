"""Internal CLI runners — invoked by ``limen.cli.geodata``.

Every entry point degrades gracefully: a missing optional dep
(``pyogrio``, ``fastmcp``) logs a clear hint and exits non-zero rather
than crashing with an ``ImportError`` traceback.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import structlog

from geodata.manifest import load_manifest

# ---------------------------------------------------------------------------
# Logging — geodata is consumed inside the Limen CLI which already
# configures structlog, but the package can also run standalone (the
# Docker entry point invokes the CLI directly), so we self-configure
# on first import with a sane default.
# ---------------------------------------------------------------------------
if not structlog.is_configured():  # pragma: no cover — exercised in container
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )

_log: structlog.stdlib.BoundLogger = structlog.get_logger("geodata")


DEFAULT_MANIFEST = Path(__file__).resolve().parent / "datasets.yaml"


def _resolve_manifest_path(override: str | None) -> Path:
    return Path(override) if override else DEFAULT_MANIFEST


async def run_list(*, manifest_path: str | None = None) -> int:
    """``limen geodata list`` — print every manifest entry as a table.

    Status / version columns will surface once the init runner lands
    in Stage B and starts writing to ``dataset_versions``; for now we
    print the manifest verbatim.
    """
    path = _resolve_manifest_path(manifest_path)
    manifest = load_manifest(path)
    rows = [
        {
            "name": d.name,
            "format": d.format.value,
            "target": d.target,
            "region": d.region or "",
            "enabled": d.enabled,
            "url": d.url,
        }
        for d in manifest.datasets
    ]
    sys.stdout.write(json.dumps({"version": manifest.version, "datasets": rows}, indent=2))
    sys.stdout.write("\n")
    _log.info(
        "geodata.list.done",
        manifest=str(path),
        datasets=len(rows),
        enabled=sum(1 for d in manifest.datasets if d.enabled),
    )
    return 0


async def run_init(
    *,
    manifest_path: str | None = None,
    only: str | None = None,
    region: str | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> int:
    """``limen geodata init`` — implementation lands in Stage B."""
    from geodata.init.runner import run_init_pipeline

    return await run_init_pipeline(
        manifest_path=_resolve_manifest_path(manifest_path),
        only=only,
        region=region,
        force=force,
        dry_run=dry_run,
    )


async def run_export_features(*, operational_dsn: str) -> int:
    """``limen geodata export-features`` — implementation lands in Stage C."""
    from geodata.exports.features import export_cell_features

    return await export_cell_features(operational_dsn=operational_dsn)


async def run_make_pmtiles() -> int:
    """``limen geodata make-pmtiles`` — implementation lands in Stage C."""
    from geodata.exports.pmtiles import make_pmtiles

    return await make_pmtiles()


async def run_mcp(*, transport: str = "stdio") -> int:
    """``limen geodata mcp`` — implementation lands in Stage D."""
    from geodata.mcp.server import run_mcp_server

    return await run_mcp_server(transport=transport)
