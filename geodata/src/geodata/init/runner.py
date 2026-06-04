"""``limen geodata init`` runner — Stage B placeholder.

The complete implementation lands in Stage B. The placeholder keeps
the CLI subcommand wired so ``limen geodata --help`` works from the
moment Stage A merges; invoking ``limen geodata init`` here logs that
the pipeline isn't built yet and returns a non-zero exit code.
"""

from __future__ import annotations

from pathlib import Path

import structlog

_log: structlog.stdlib.BoundLogger = structlog.get_logger("geodata.init")


async def run_init_pipeline(
    *,
    manifest_path: Path,
    only: str | None = None,
    region: str | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> int:
    _log.warning(
        "geodata.init.not_implemented_yet",
        manifest=str(manifest_path),
        only=only,
        region=region,
        force=force,
        dry_run=dry_run,
        hint="init runner lands in Stage B",
    )
    return 1
