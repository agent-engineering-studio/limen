"""Filesystem-backed ObjectStore.

This is the default backend for dev/demo runs. Files are written under a
configurable root directory. Path traversal (``..``) is rejected.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from limen.data.object_store.base import ObjectStore


class FilesystemObjectStore(ObjectStore):
    """Stores blobs under ``root`` using their key as a relative path."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        if not key or key.startswith("/"):
            raise ValueError(f"Invalid object-store key: {key!r}")
        target = (self._root / key).resolve()
        if not str(target).startswith(str(self._root)):
            raise ValueError(f"Path traversal rejected: {key!r}")
        return target

    async def put(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str | None = None,  # noqa: ARG002 — filesystem has no MIME concept
    ) -> str:
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(target.write_bytes, data)
        return str(target)

    async def get(self, key: str) -> bytes:
        target = self._resolve(key)
        if not target.exists():
            raise FileNotFoundError(key)
        return await asyncio.to_thread(target.read_bytes)

    async def exists(self, key: str) -> bool:
        return await asyncio.to_thread(self._resolve(key).exists)

    async def url(self, key: str) -> str:
        return self._resolve(key).as_uri()

    async def delete(self, key: str) -> None:
        target = self._resolve(key)
        if target.exists():
            await asyncio.to_thread(target.unlink)
