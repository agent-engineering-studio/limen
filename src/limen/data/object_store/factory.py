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
        * ``s3``         — :class:`S3ObjectStore` (requires `storage` group).
        * ``azure_blob`` — :class:`AzureBlobObjectStore` (requires `storage`).
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

    if cfg.backend is ObjectStoreBackend.AZURE_BLOB:
        if not cfg.container:
            raise ValueError("OBJECT_STORE__CONTAINER is required when backend=azure_blob")
        if cfg.connection_string is None:
            raise ValueError("OBJECT_STORE__CONNECTION_STRING is required when backend=azure_blob")
        from limen.data.object_store.azure_blob import AzureBlobObjectStore

        return AzureBlobObjectStore(
            container=cfg.container,
            connection_string=cfg.connection_string,
            prefix=cfg.prefix,
        )

    raise ValueError(f"Unknown object-store backend: {cfg.backend!r}")
