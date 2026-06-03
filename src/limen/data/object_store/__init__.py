"""Object-store abstraction (filesystem / S3 / Azure Blob)."""

from limen.data.object_store.base import ObjectStore
from limen.data.object_store.factory import build_object_store

__all__ = ["ObjectStore", "build_object_store"]
