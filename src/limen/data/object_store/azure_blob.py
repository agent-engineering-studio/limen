"""Azure Blob Storage-backed ObjectStore.

Uses ``azure-storage-blob``. The import is guarded so the module can sit in
the package even when the ``storage`` dependency group has not been installed.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from limen.data.object_store.base import ObjectStore

if TYPE_CHECKING:
    from pydantic import SecretStr


class AzureBlobObjectStore(ObjectStore):
    """Azure Blob implementation. Sync calls off-loaded via ``asyncio.to_thread``."""

    def __init__(
        self,
        *,
        container: str,
        connection_string: SecretStr,
        prefix: str = "",
    ) -> None:
        try:
            from azure.storage.blob import BlobServiceClient
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "Azure Blob ObjectStore requires the optional 'storage' "
                "dependency group: `uv sync --group storage`."
            ) from e

        self._container_name = container
        self._prefix = prefix.strip("/")
        self._service = BlobServiceClient.from_connection_string(
            connection_string.get_secret_value()
        )
        self._container = self._service.get_container_client(container)

    def _name(self, key: str) -> str:
        return f"{self._prefix}/{key}".lstrip("/") if self._prefix else key

    async def put(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str | None = None,
    ) -> str:
        from azure.storage.blob import ContentSettings

        blob = self._container.get_blob_client(self._name(key))
        cs = ContentSettings(content_type=content_type) if content_type else None
        await asyncio.to_thread(blob.upload_blob, data, overwrite=True, content_settings=cs)
        return await self.url(key)

    async def get(self, key: str) -> bytes:
        from azure.core.exceptions import ResourceNotFoundError

        blob = self._container.get_blob_client(self._name(key))
        try:
            stream = await asyncio.to_thread(blob.download_blob)
        except ResourceNotFoundError as e:
            raise FileNotFoundError(key) from e
        return await asyncio.to_thread(stream.readall)

    async def exists(self, key: str) -> bool:
        blob = self._container.get_blob_client(self._name(key))
        return await asyncio.to_thread(blob.exists)

    async def url(self, key: str) -> str:
        return f"azure://{self._container_name}/{self._name(key)}"

    async def delete(self, key: str) -> None:
        from azure.core.exceptions import ResourceNotFoundError

        blob = self._container.get_blob_client(self._name(key))
        try:
            await asyncio.to_thread(blob.delete_blob)
        except ResourceNotFoundError:
            return
