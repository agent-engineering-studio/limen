"""Factory that builds an :class:`ObjectStore` from settings.

This is the only place application code asks "which backend?". Everything
else only knows about the :class:`ObjectStore` Protocol.
"""

from __future__ import annotations

from limen.config.settings import (
    ObjectStoreBackend,
    ObjectStoreSettings,
    get_settings,
)
from limen.data.object_store.base import ObjectStore
from limen.data.object_store.filesystem import FilesystemObjectStore


def build_object_store(settings: ObjectStoreSettings | None = None) -> ObjectStore:
    """Construct an :class:`ObjectStore` from configuration.

    Backends:
        * ``filesystem`` — :class:`FilesystemObjectStore` (default).
        * ``s3``         — :class:`S3ObjectStore`, targeting any S3-compatible
          endpoint (MinIO, Aruba Cloud Object Storage, R2, B2). Requires the
          optional ``storage`` dependency group.
    """
    cfg = settings or get_settings().object_store

    if cfg.backend is ObjectStoreBackend.FILESYSTEM:
        return FilesystemObjectStore(cfg.root)

    if cfg.backend is ObjectStoreBackend.S3:
        if not cfg.bucket:
            raise ValueError("OBJECT_STORE__BUCKET is required when backend=s3")
        from limen.data.object_store.s3 import S3ObjectStore

        return S3ObjectStore(
            bucket=cfg.bucket,
            prefix=cfg.prefix,
            region=cfg.region,
            endpoint_url=cfg.endpoint_url,
            access_key_id=cfg.access_key_id,
            secret_access_key=cfg.secret_access_key,
        )

    raise ValueError(f"Unknown object-store backend: {cfg.backend!r}")
