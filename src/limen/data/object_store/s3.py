"""S3-backed ObjectStore.

Uses ``boto3``. The import is guarded so the module can sit in the package
even when the ``storage`` dependency group has not been installed.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from limen.data.object_store.base import ObjectStore

if TYPE_CHECKING:
    from pydantic import SecretStr


class S3ObjectStore(ObjectStore):
    """S3 implementation. Synchronous boto3 calls are off-loaded to a thread."""

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str = "",
        region: str | None = None,
        endpoint_url: str | None = None,
        access_key_id: SecretStr | None = None,
        secret_access_key: SecretStr | None = None,
    ) -> None:
        try:
            import boto3
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "S3 ObjectStore requires the optional 'storage' dependency "
                "group: `uv sync --group storage`."
            ) from e

        self._bucket = bucket
        self._prefix = prefix.strip("/")
        client_kwargs: dict[str, Any] = {}
        if region:
            client_kwargs["region_name"] = region
        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url
        if access_key_id is not None:
            client_kwargs["aws_access_key_id"] = access_key_id.get_secret_value()
        if secret_access_key is not None:
            client_kwargs["aws_secret_access_key"] = secret_access_key.get_secret_value()

        self._client = boto3.client("s3", **client_kwargs)

    def _key(self, key: str) -> str:
        return f"{self._prefix}/{key}".lstrip("/") if self._prefix else key

    async def put(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str | None = None,
    ) -> str:
        kwargs: dict[str, Any] = {"Bucket": self._bucket, "Key": self._key(key), "Body": data}
        if content_type:
            kwargs["ContentType"] = content_type
        await asyncio.to_thread(self._client.put_object, **kwargs)
        return await self.url(key)

    async def get(self, key: str) -> bytes:
        try:
            resp = await asyncio.to_thread(
                self._client.get_object, Bucket=self._bucket, Key=self._key(key)
            )
        except self._client.exceptions.NoSuchKey as e:
            raise FileNotFoundError(key) from e
        body = resp["Body"]
        return await asyncio.to_thread(body.read)

    async def exists(self, key: str) -> bool:
        try:
            await asyncio.to_thread(
                self._client.head_object, Bucket=self._bucket, Key=self._key(key)
            )
        except self._client.exceptions.ClientError:
            return False
        return True

    async def url(self, key: str) -> str:
        return f"s3://{self._bucket}/{self._key(key)}"

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket, Key=self._key(key))
