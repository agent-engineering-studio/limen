"""ObjectStore Protocol.

All implementations expose the same minimal API. The application code only
imports this Protocol; the concrete backend is decided by configuration via
:func:`limen.data.object_store.factory.build_object_store`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ObjectStore(Protocol):
    """A flat blob store keyed by string paths.

    Implementations must be thread- and async-safe enough for the standard
    Limen use cases: ingestion writers, occasional reads from API handlers.
    """

    async def put(self, key: str, data: bytes, *, content_type: str | None = None) -> str:
        """Store ``data`` at ``key`` and return a backend-relative URL/path."""

    async def get(self, key: str) -> bytes:
        """Return the bytes stored at ``key``. Raises ``FileNotFoundError`` if absent."""

    async def exists(self, key: str) -> bool:
        """Return whether ``key`` exists in the store."""

    async def url(self, key: str) -> str:
        """Return an opaque, backend-specific URL/URI for ``key``."""

    async def delete(self, key: str) -> None:
        """Delete ``key``. No-op if absent."""
