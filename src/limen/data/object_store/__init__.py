"""Object-store abstraction (filesystem / S3-compatible).

The S3 backend targets S3-compatible endpoints — MinIO containerised next
to the app, Aruba Cloud Object Storage, R2, B2 — via
``OBJECT_STORE__ENDPOINT_URL``. It is not specific to AWS.
"""

from limen.data.object_store.base import ObjectStore
from limen.data.object_store.factory import build_object_store

__all__ = ["ObjectStore", "build_object_store"]
