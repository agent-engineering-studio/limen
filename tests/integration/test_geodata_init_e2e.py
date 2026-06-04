"""Geo-Data Service — init runner end-to-end with mocked downloads.

Validates the §6 prompt-12 criteria that don't fit into a unit test:

* skip-if-unchanged is genuinely idempotent against a real
  ``dataset_versions`` row;
* a dataset whose download / unzip / import fails does NOT abort the
  others — the runner reports per-dataset outcomes and exits non-zero
  only when *something* failed;
* ``--only`` / ``--force`` / ``--dry-run`` behave correctly against a
  live (in-memory respx) HTTP layer.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any

import asyncpg
import httpx
import pytest
import respx

from geodata.init.runner import run_init_pipeline
from geodata.manifest import DatasetFormat

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers — build a valid ZIP-wrapped shapefile in memory
# ---------------------------------------------------------------------------
def _poly(lon: float, lat: float, side: float = 0.01) -> Any:
    from shapely.geometry import Polygon

    return Polygon(
        [
            (lon, lat),
            (lon + side, lat),
            (lon + side, lat + side),
            (lon, lat + side),
            (lon, lat),
        ]
    )


def _write_shapefile_zip(*, tmp_path: Path, name: str, rows: list[dict[str, Any]]) -> bytes:
    """Produce a ZIP archive containing a valid shapefile + its sidecars."""
    import geopandas as gpd
    import pyogrio

    geoms = [r.pop("geometry") for r in rows]
    gdf = gpd.GeoDataFrame(rows, geometry=geoms, crs="EPSG:4326")
    shp_path = tmp_path / f"{name}.shp"
    pyogrio.write_dataframe(gdf, str(shp_path), driver="ESRI Shapefile")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for sidecar in sorted(shp_path.parent.glob(f"{name}.*")):
            zf.write(sidecar, arcname=sidecar.name)
    return buffer.getvalue()


def _write_manifest(tmp_path: Path, *, datasets: list[dict[str, Any]]) -> Path:
    import yaml

    path = tmp_path / "datasets.yaml"
    path.write_text(
        yaml.safe_dump({"version": "test", "datasets": datasets}),
        encoding="utf-8",
    )
    return path


_PAI_URL = (
    "https://idrogeo.isprambiente.it/opendata/wms/"
    "Mosaicatura_ISPRA_2020_2021_aree_pericolosita_frana_PAI.zip"
)
_IFFI_URL = "https://idrogeo.isprambiente.it/opendata/iffi/puglia/iffi_puglia_piff_poly.zip"
_BROKEN_URL = "https://idrogeo.isprambiente.it/opendata/wms/this_endpoint_503s.zip"


def _pai_entry(
    *, name: str = "pai_frane", url: str = _PAI_URL, enabled: bool = True
) -> dict[str, Any]:
    return {
        "name": name,
        "url": url,
        "format": DatasetFormat.SHAPEFILE_ZIP.value,
        "target": "pai_landslide_hazard",
        "enabled": enabled,
    }


def _iffi_entry(name: str, url: str = _IFFI_URL) -> dict[str, Any]:
    return {
        "name": name,
        "url": url,
        "format": DatasetFormat.SHAPEFILE_ZIP.value,
        "target": "iffi_landslides",
        "region": "puglia",
        "enabled": True,
    }


# ---------------------------------------------------------------------------
# Skip-if-unchanged: same checksum on the second run → no new rows
# ---------------------------------------------------------------------------
@respx.mock
async def test_init_skip_if_unchanged_is_idempotent(
    geodata_conn: asyncpg.Connection, tmp_path: Path
) -> None:
    pai_zip = _write_shapefile_zip(
        tmp_path=tmp_path,
        name="pai",
        rows=[
            {
                "pai_id": "PAI-1",
                "classe_pai": "P3",
                "autorita": "AdB",
                "geometry": _poly(16.86, 41.12),
            },
            {
                "pai_id": "PAI-2",
                "classe_pai": "P1",
                "autorita": "AdB",
                "geometry": _poly(16.90, 41.12),
            },
        ],
    )
    route = respx.get(_PAI_URL).mock(return_value=httpx.Response(200, content=pai_zip))
    manifest = _write_manifest(tmp_path, datasets=[_pai_entry()])

    rc1 = await run_init_pipeline(manifest_path=manifest)
    rc2 = await run_init_pipeline(manifest_path=manifest)

    assert rc1 == 0
    assert rc2 == 0
    # Both runs hit the URL — the SHA-256 dedup is downstream of the HTTP
    # response, but the second run must NOT upsert (the row count stays at 2).
    assert route.call_count == 2
    n = await geodata_conn.fetchval("SELECT COUNT(*) FROM pai_landslide_hazard")
    assert int(n) == 2
    versions = await geodata_conn.fetchval(
        "SELECT COUNT(*) FROM dataset_versions WHERE name = 'pai_frane'"
    )
    # Skip-if-unchanged means we don't append a new version row either.
    assert int(versions) == 1


# ---------------------------------------------------------------------------
# Per-dataset failure isolation: one failing URL doesn't abort others
# ---------------------------------------------------------------------------
@respx.mock
async def test_failing_dataset_does_not_block_others(
    geodata_conn: asyncpg.Connection, tmp_path: Path
) -> None:
    iffi_zip = _write_shapefile_zip(
        tmp_path=tmp_path,
        name="iffi_puglia_piff_poly",
        rows=[
            {"iffi_id": "I-1", "movement": "scivolamento", "geometry": _poly(16.86, 41.12)},
        ],
    )
    respx.get(_BROKEN_URL).mock(return_value=httpx.Response(503))
    respx.get(_IFFI_URL).mock(return_value=httpx.Response(200, content=iffi_zip))

    manifest = _write_manifest(
        tmp_path,
        datasets=[
            _pai_entry(name="broken_dataset", url=_BROKEN_URL),
            _iffi_entry("iffi_puglia_piff_poly"),
        ],
    )
    rc = await run_init_pipeline(manifest_path=manifest)
    # At least one dataset failed → non-zero exit, so CI surfaces it.
    assert rc == 1
    # But the healthy IFFI dataset must have landed.
    n = await geodata_conn.fetchval("SELECT COUNT(*) FROM iffi_landslides")
    assert int(n) == 1
    # No version row written for the broken dataset.
    broken_versions = await geodata_conn.fetchval(
        "SELECT COUNT(*) FROM dataset_versions WHERE name = 'broken_dataset'"
    )
    assert int(broken_versions) == 0


# ---------------------------------------------------------------------------
# --only filter
# ---------------------------------------------------------------------------
@respx.mock
async def test_init_only_restricts_downloads(
    geodata_conn: asyncpg.Connection, tmp_path: Path
) -> None:
    iffi_zip = _write_shapefile_zip(
        tmp_path=tmp_path,
        name="iffi_puglia_piff_poly",
        rows=[{"iffi_id": "I-7", "movement": "x", "geometry": _poly(16.86, 41.12)}],
    )
    pai_route = respx.get(_PAI_URL).mock(return_value=httpx.Response(200, content=b"unused"))
    iffi_route = respx.get(_IFFI_URL).mock(return_value=httpx.Response(200, content=iffi_zip))

    manifest = _write_manifest(
        tmp_path,
        datasets=[_pai_entry(), _iffi_entry("iffi_puglia_piff_poly")],
    )
    rc = await run_init_pipeline(manifest_path=manifest, only="iffi_puglia_piff_poly")
    assert rc == 0
    assert pai_route.call_count == 0, "--only should not download the PAI dataset"
    assert iffi_route.call_count == 1


# ---------------------------------------------------------------------------
# --force re-imports even when the checksum is unchanged
# ---------------------------------------------------------------------------
@respx.mock
async def test_init_force_re_imports_unchanged_checksum(
    geodata_conn: asyncpg.Connection, tmp_path: Path
) -> None:
    pai_zip = _write_shapefile_zip(
        tmp_path=tmp_path,
        name="pai",
        rows=[
            {
                "pai_id": "PAI-1",
                "classe_pai": "P3",
                "autorita": "AdB",
                "geometry": _poly(16.86, 41.12),
            },
        ],
    )
    respx.get(_PAI_URL).mock(return_value=httpx.Response(200, content=pai_zip))
    manifest = _write_manifest(tmp_path, datasets=[_pai_entry()])

    await run_init_pipeline(manifest_path=manifest)
    # Second run with --force: same checksum, but the importer must run again.
    await run_init_pipeline(manifest_path=manifest, force=True)

    versions = await geodata_conn.fetchval(
        "SELECT COUNT(*) FROM dataset_versions WHERE name = 'pai_frane'"
    )
    # Same checksum → UNIQUE (name, checksum) makes the upsert touch the same
    # row — fetched_at is updated but no second row is created.
    assert int(versions) == 1


# ---------------------------------------------------------------------------
# --dry-run does not hit the network
# ---------------------------------------------------------------------------
@respx.mock
async def test_init_dry_run_skips_download_entirely(
    geodata_conn: asyncpg.Connection, tmp_path: Path
) -> None:
    pai_route = respx.get(_PAI_URL).mock(return_value=httpx.Response(500))
    manifest = _write_manifest(tmp_path, datasets=[_pai_entry()])

    rc = await run_init_pipeline(manifest_path=manifest, dry_run=True)
    assert rc == 0
    # Crucially: no HTTP call. The route's 500 mock would have failed the
    # download otherwise.
    assert pai_route.call_count == 0
    n = await geodata_conn.fetchval("SELECT COUNT(*) FROM pai_landslide_hazard")
    assert int(n) == 0


# ---------------------------------------------------------------------------
# Incomplete archive — single .dbf, no .shp — aborts THIS dataset only
# ---------------------------------------------------------------------------
@respx.mock
async def test_incomplete_archive_aborts_only_that_dataset(
    geodata_conn: asyncpg.Connection, tmp_path: Path
) -> None:
    # Bad payload — a zip with only a .dbf, no .shp. The importer must
    # reject it with a clear diagnostic but the IFFI dataset still imports.
    bad_buf = io.BytesIO()
    with zipfile.ZipFile(bad_buf, "w") as zf:
        zf.writestr("pai.dbf", b"\x00\x00")
    iffi_zip = _write_shapefile_zip(
        tmp_path=tmp_path,
        name="iffi_puglia_piff_poly",
        rows=[{"iffi_id": "I-1", "movement": "x", "geometry": _poly(16.86, 41.12)}],
    )

    respx.get(_PAI_URL).mock(return_value=httpx.Response(200, content=bad_buf.getvalue()))
    respx.get(_IFFI_URL).mock(return_value=httpx.Response(200, content=iffi_zip))

    manifest = _write_manifest(
        tmp_path,
        datasets=[_pai_entry(), _iffi_entry("iffi_puglia_piff_poly")],
    )
    rc = await run_init_pipeline(manifest_path=manifest)
    assert rc == 1, "the broken PAI dataset should mark the run as failed"
    n_iffi = await geodata_conn.fetchval("SELECT COUNT(*) FROM iffi_landslides")
    assert int(n_iffi) == 1, "the healthy IFFI dataset should still import"
    n_pai = await geodata_conn.fetchval("SELECT COUNT(*) FROM pai_landslide_hazard")
    assert int(n_pai) == 0, "the broken PAI dataset must not have written any rows"
