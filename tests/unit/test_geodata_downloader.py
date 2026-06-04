"""Geo-Data Service — streaming download + safe unzip."""

from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

import httpx
import pytest
import respx

from geodata.init.downloader import download_to_file, safe_unzip


# ---------------------------------------------------------------------------
# download_to_file
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@respx.mock
async def test_download_streams_to_disk_and_computes_sha(tmp_path: Path) -> None:
    body = b"hello idrogeo\n" * 1000
    respx.get("https://idrogeo.isprambiente.it/opendata/foo.zip").mock(
        return_value=httpx.Response(
            200, content=body, headers={"etag": '"abc123"', "last-modified": "yesterday"}
        )
    )
    dest = tmp_path / "foo.zip"
    result = await download_to_file(
        url="https://idrogeo.isprambiente.it/opendata/foo.zip", dest=dest
    )
    assert dest.exists()
    assert dest.read_bytes() == body
    assert result.checksum == hashlib.sha256(body).hexdigest()
    assert result.etag == '"abc123"'
    assert result.last_modified == "yesterday"
    assert result.content_length == len(body)


@pytest.mark.asyncio
@respx.mock
async def test_download_retries_5xx_then_succeeds(tmp_path: Path) -> None:
    route = respx.get("https://idrogeo.isprambiente.it/opendata/flap.zip").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(200, content=b"second-try-wins"),
        ]
    )
    dest = tmp_path / "flap.zip"
    result = await download_to_file(
        url="https://idrogeo.isprambiente.it/opendata/flap.zip", dest=dest
    )
    assert route.call_count == 2
    assert dest.read_bytes() == b"second-try-wins"
    assert result.content_length == len(b"second-try-wins")


# ---------------------------------------------------------------------------
# safe_unzip
# ---------------------------------------------------------------------------
def _make_zip(tmp_path: Path, entries: dict[str, bytes]) -> Path:
    archive = tmp_path / "archive.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return archive


def test_safe_unzip_extracts_into_dest(tmp_path: Path) -> None:
    archive = _make_zip(
        tmp_path,
        {
            "data/foo.shp": b"shapefile bytes",
            "data/foo.dbf": b"attr bytes",
        },
    )
    out = tmp_path / "out"
    extracted = safe_unzip(archive=archive, dest_dir=out)
    names = {p.name for p in extracted}
    assert names == {"foo.shp", "foo.dbf"}


def test_safe_unzip_rejects_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../escape.txt", b"naughty")
    with pytest.raises(ValueError, match="path-traversal"):
        safe_unzip(archive=archive, dest_dir=tmp_path / "out")


def test_safe_unzip_rejects_absolute_paths(tmp_path: Path) -> None:
    archive = tmp_path / "absolute.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        info = zipfile.ZipInfo(filename="/etc/passwd")
        with io.BytesIO(b"naughty") as src:
            zf.writestr(info, src.read())
    with pytest.raises(ValueError, match="path-traversal"):
        safe_unzip(archive=archive, dest_dir=tmp_path / "out")


def test_safe_unzip_skips_directory_entries(tmp_path: Path) -> None:
    archive = tmp_path / "dirs.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("subdir/", b"")
        zf.writestr("subdir/file.txt", b"hello")
    out = tmp_path / "out"
    extracted = safe_unzip(archive=archive, dest_dir=out)
    assert {p.name for p in extracted} == {"file.txt"}
    assert (out / "subdir" / "file.txt").read_bytes() == b"hello"


def test_safe_unzip_missing_archive_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        safe_unzip(archive=tmp_path / "missing.zip", dest_dir=tmp_path / "out")
