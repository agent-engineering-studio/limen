"""Filesystem ObjectStore tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from limen.data.object_store.filesystem import FilesystemObjectStore


async def test_put_get_exists_delete(tmp_path: Path) -> None:
    store = FilesystemObjectStore(tmp_path)

    assert await store.exists("foo/bar.bin") is False
    location = await store.put("foo/bar.bin", b"hello")
    assert Path(location).exists()
    assert await store.exists("foo/bar.bin") is True
    assert await store.get("foo/bar.bin") == b"hello"
    await store.delete("foo/bar.bin")
    assert await store.exists("foo/bar.bin") is False


async def test_get_missing_raises(tmp_path: Path) -> None:
    store = FilesystemObjectStore(tmp_path)
    with pytest.raises(FileNotFoundError):
        await store.get("nope.bin")


async def test_path_traversal_is_rejected(tmp_path: Path) -> None:
    store = FilesystemObjectStore(tmp_path)
    with pytest.raises(ValueError, match="traversal"):
        await store.put("../escape.bin", b"x")


async def test_factory_default_is_filesystem(tmp_path: Path) -> None:
    from limen.config.settings import ObjectStoreSettings
    from limen.data.object_store.factory import build_object_store

    store = build_object_store(ObjectStoreSettings(root=tmp_path))
    assert isinstance(store, FilesystemObjectStore)
