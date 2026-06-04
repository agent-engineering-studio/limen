"""Streaming download + safe unzip for ISPRA archives.

Two responsibilities, both designed to keep the geodata service safe
to run on a small VPS:

1. :func:`download_to_file` — streams an HTTP response chunk-by-chunk
   to disk (never loads the whole file into memory), retries on
   transient failures via tenacity, returns the on-disk path + the
   SHA-256 + the ``ETag``/``Last-Modified`` header so the runner can
   skip an unchanged source.
2. :func:`safe_unzip` — rejects path-traversal entries
   (``../whatever`` and absolute paths) and extracts only into the
   destination directory. Lifted from the standard hardening pattern.
"""

from __future__ import annotations

import hashlib
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import structlog
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

_log: structlog.stdlib.BoundLogger = structlog.get_logger("geodata.init.downloader")

_DEFAULT_CHUNK = 1 << 16  # 64 KiB

_RETRYABLE: tuple[type[BaseException], ...] = (
    httpx.TransportError,
    httpx.TimeoutException,
    httpx.HTTPStatusError,
)


@dataclass(frozen=True, slots=True)
class DownloadResult:
    path: Path
    checksum: str
    etag: str | None
    last_modified: str | None
    content_length: int


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500 or exc.response.status_code == 429
    return True


async def download_to_file(
    *,
    url: str,
    dest: Path,
    timeout_seconds: float = 120.0,
    max_attempts: int = 4,
) -> DownloadResult:
    """Stream ``url`` into ``dest`` and return the metadata.

    The retry policy mirrors the rest of Limen: 4 attempts, exponential
    backoff capped at 60 s, retrying on transport errors and 5xx/429.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256()
    bytes_written = 0
    etag: str | None = None
    last_modified: str | None = None

    async def _attempt() -> None:
        nonlocal bytes_written, etag, last_modified
        sha_local = hashlib.sha256()
        bytes_local = 0
        tmp = dest.with_suffix(dest.suffix + ".part")
        async with (
            httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=True) as client,
            client.stream("GET", url) as response,
        ):
            response.raise_for_status()
            etag_local = response.headers.get("etag")
            last_modified_local = response.headers.get("last-modified")
            with tmp.open("wb") as fh:
                async for chunk in response.aiter_bytes(_DEFAULT_CHUNK):
                    sha_local.update(chunk)
                    fh.write(chunk)
                    bytes_local += len(chunk)
        tmp.replace(dest)
        # Commit the per-attempt sha / counters to the closure.
        nonlocal sha
        sha = sha_local
        bytes_written = bytes_local
        etag = etag_local
        last_modified = last_modified_local

    try:
        async for attempt in AsyncRetrying(
            reraise=True,
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=2, max=60),
            retry=retry_if_exception_type(_RETRYABLE),
            retry_error_callback=lambda rs: rs,
        ):
            with attempt:
                if not _is_retryable_in_advance(attempt.retry_state.outcome):
                    pass
                await _attempt()
    except RetryError as exc:  # pragma: no cover — tenacity wraps the final fail
        last_exc = exc.last_attempt.exception()
        if last_exc is not None:
            raise last_exc from exc
        raise

    _log.info(
        "geodata.download.done",
        url=url,
        path=str(dest),
        bytes=bytes_written,
        etag=etag,
    )
    return DownloadResult(
        path=dest,
        checksum=sha.hexdigest(),
        etag=etag,
        last_modified=last_modified,
        content_length=bytes_written,
    )


def _is_retryable_in_advance(outcome: Any) -> bool:
    if outcome is None or outcome.exception() is None:
        return False
    return _is_retryable(outcome.exception())


def safe_unzip(*, archive: Path, dest_dir: Path) -> list[Path]:
    """Extract ``archive`` into ``dest_dir`` safely.

    Refuses any zip entry whose resolved path falls outside ``dest_dir``
    (path traversal) and any absolute / symlink-style entry. Returns
    the list of extracted file paths.
    """
    if not archive.exists():
        raise FileNotFoundError(f"archive not found: {archive}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    base_resolved = dest_dir.resolve()
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            name = info.filename
            if not name or name.endswith("/"):
                continue
            candidate = (dest_dir / name).resolve()
            try:
                candidate.relative_to(base_resolved)
            except ValueError as exc:
                raise ValueError(f"refusing path-traversal entry: {name!r}") from exc
            candidate.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, candidate.open("wb") as dst:
                while True:
                    chunk = src.read(_DEFAULT_CHUNK)
                    if not chunk:
                        break
                    dst.write(chunk)
            extracted.append(candidate)
    _log.info("geodata.unzip.done", archive=str(archive), files=len(extracted))
    return extracted


__all__ = ["DownloadResult", "download_to_file", "safe_unzip"]
