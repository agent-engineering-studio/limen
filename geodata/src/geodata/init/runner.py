"""``limen geodata init`` runner — download → unzip → import.

For each enabled dataset:

1. Streaming download (with retries) to a temp dir.
2. Skip-if-unchanged: SHA-256 against the most-recent
   ``dataset_versions`` row for the same name.
3. Safe unzip (path-traversal proof) — JSONs are written directly,
   no archive expansion.
4. Format-specific import via :func:`geodata.init.importers.import_dataset`.
5. Insert a new ``dataset_versions`` row.
6. Clean temp files (even on failure).

One failing dataset never aborts the others; the runner returns a
non-zero exit code when *any* dataset failed so CI surfaces it.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import structlog

from geodata.db import (
    connect,
    ensure_schema,
    get_existing_checksum,
    insert_dataset_version,
)
from geodata.init.downloader import download_to_file, safe_unzip
from geodata.init.importers import import_dataset
from geodata.manifest import DatasetSpec, load_manifest

_log: structlog.stdlib.BoundLogger = structlog.get_logger("geodata.init")


@dataclass(frozen=True, slots=True)
class DatasetOutcome:
    name: str
    status: str  # imported | skipped_unchanged | failed | dry_run | filtered
    rows: int = 0
    notes: str = ""
    error: str | None = None


def _filter_specs(
    specs: tuple[DatasetSpec, ...],
    *,
    only: str | None,
    region: str | None,
) -> tuple[DatasetSpec, ...]:
    out = tuple(d for d in specs if d.enabled)
    if only:
        wanted = {name.strip() for name in only.split(",") if name.strip()}
        out = tuple(d for d in out if d.name in wanted)
    if region:
        out = tuple(d for d in out if (d.region or "").lower() == region.lower())
    return out


async def _process_one(
    spec: DatasetSpec,
    *,
    workdir: Path,
    force: bool,
    dry_run: bool,
) -> DatasetOutcome:
    archive_path = workdir / f"{spec.name}.bin"
    extract_dir = workdir / f"{spec.name}.extracted"

    if dry_run:
        _log.info("geodata.init.dry_run", name=spec.name, url=spec.url)
        return DatasetOutcome(name=spec.name, status="dry_run")

    try:
        download = await download_to_file(url=spec.url, dest=archive_path)
    except Exception as exc:
        _log.warning(
            "geodata.init.download_failed",
            name=spec.name,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return DatasetOutcome(name=spec.name, status="failed", error=str(exc), notes="download")

    async with connect() as conn:
        await ensure_schema(conn)
        if not force:
            existing = await get_existing_checksum(conn, name=spec.name)
            if existing == download.checksum:
                _log.info(
                    "geodata.init.skip_unchanged",
                    name=spec.name,
                    checksum=existing[:12],
                )
                return DatasetOutcome(
                    name=spec.name, status="skipped_unchanged", notes=existing[:12]
                )

        # Extract (zip) or hand the JSON file straight to the importer.
        if spec.format.value == "json":
            extracted = [download.path]
        else:
            try:
                extracted = safe_unzip(archive=download.path, dest_dir=extract_dir)
            except Exception as exc:
                _log.warning(
                    "geodata.init.unzip_failed",
                    name=spec.name,
                    error=str(exc),
                )
                return DatasetOutcome(
                    name=spec.name, status="failed", error=str(exc), notes="unzip"
                )

        try:
            outcome = await import_dataset(
                conn,
                spec=spec,
                extracted=extracted,
                dataset_version_id=None,
            )
        except Exception as exc:
            _log.warning(
                "geodata.init.import_failed",
                name=spec.name,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return DatasetOutcome(name=spec.name, status="failed", error=str(exc), notes="import")

        await insert_dataset_version(
            conn,
            name=spec.name,
            url=spec.url,
            checksum=download.checksum,
            etag=download.etag,
            row_count=outcome.rows_written,
            metadata={"target": spec.target, "notes": outcome.notes},
        )

    _log.info(
        "geodata.init.dataset_done",
        name=spec.name,
        rows=outcome.rows_written,
        notes=outcome.notes,
    )
    return DatasetOutcome(
        name=spec.name,
        status="imported",
        rows=outcome.rows_written,
        notes=outcome.notes,
    )


async def run_init_pipeline(
    *,
    manifest_path: Path,
    only: str | None = None,
    region: str | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> int:
    """Run the init pipeline over the manifest. Returns the CLI exit code."""
    manifest = load_manifest(manifest_path)
    specs = _filter_specs(manifest.datasets, only=only, region=region)
    if not specs:
        _log.info(
            "geodata.init.no_targets",
            manifest=str(manifest_path),
            only=only,
            region=region,
        )
        return 0

    workdir = Path(tempfile.mkdtemp(prefix="geodata-init-"))
    try:
        outcomes: list[DatasetOutcome] = []
        for spec in specs:
            outcome = await _process_one(spec, workdir=workdir, force=force, dry_run=dry_run)
            outcomes.append(outcome)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    summary = {
        "imported": sum(1 for o in outcomes if o.status == "imported"),
        "skipped_unchanged": sum(1 for o in outcomes if o.status == "skipped_unchanged"),
        "failed": sum(1 for o in outcomes if o.status == "failed"),
        "dry_run": sum(1 for o in outcomes if o.status == "dry_run"),
    }
    _log.info(
        "geodata.init.summary",
        datasets=len(outcomes),
        **summary,
    )
    return 1 if summary["failed"] else 0


__all__ = ["DatasetOutcome", "run_init_pipeline"]
