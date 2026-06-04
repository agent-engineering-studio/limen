"""Geo-Data Service — MCP tools end-to-end against a seeded PostGIS.

Validates the §6 prompt-12 criterion: "MCP tools against a seeded
test DB (testcontainers): hazard_at returns the right class for a
known point; iffi_query decodes attributes; refresh requires the
admin token."

The tool layer is already unit-tested with a fake conn; this file
walks the same code paths against a real asyncpg connection to the
geodata container so PostGIS / lookup-table JOIN semantics are
exercised end-to-end.
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

import asyncpg
import pytest

from geodata.mcp.tools import (
    MCP_ADMIN_TOKEN_ENV,
    RefreshAuthError,
    dataset_status,
    hazard_at,
    iffi_query,
    pai_summary,
    refresh,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Seed helpers — every test starts from a clean geodata_conn (truncated by
# the conftest fixture), then seeds exactly what it needs.
# ---------------------------------------------------------------------------
async def _seed_pai(
    conn: asyncpg.Connection,
    *,
    pai_id: str,
    hazard_class: str,
    bbox: tuple[float, float, float, float],
    region: str | None = None,
    authority: str = "AdB-Test",
) -> None:
    min_lon, min_lat, max_lon, max_lat = bbox
    wkt = (
        f"MULTIPOLYGON((("
        f"{min_lon} {min_lat}, {max_lon} {min_lat}, {max_lon} {max_lat}, "
        f"{min_lon} {max_lat}, {min_lon} {min_lat}"
        f")))"
    )
    await conn.execute(
        """
        INSERT INTO pai_landslide_hazard (
            pai_id, hazard_class, authority, region, geom, attributes
        ) VALUES (
            $1, $2, $3, $4,
            ST_SetSRID(ST_GeomFromText($5), 4326),
            '{}'::jsonb
        )
        """,
        pai_id,
        hazard_class,
        authority,
        region,
        wkt,
    )


async def _seed_iffi(
    conn: asyncpg.Connection,
    *,
    iffi_id: str,
    region: str,
    geom_type: str,
    movement_type: str | None,
    point: tuple[float, float],
) -> None:
    lon, lat = point
    wkt = f"POINT({lon} {lat})"
    composite_id = f"{region}|{iffi_id}|{geom_type}"
    await conn.execute(
        """
        INSERT INTO iffi_landslides (
            id, iffi_id, region, geom_type, movement_type,
            geom, attributes
        ) VALUES (
            $1, $2, $3, $4, $5,
            ST_SetSRID(ST_GeomFromText($6), 4326),
            '{}'::jsonb
        )
        """,
        composite_id,
        iffi_id,
        region,
        geom_type,
        movement_type,
        wkt,
    )


async def _seed_dizionario(
    conn: asyncpg.Connection,
    *,
    code: str,
    label: str,
) -> None:
    await conn.execute(
        "INSERT INTO iffi_lookup_movements (code, label) VALUES ($1, $2) "
        "ON CONFLICT (code) DO UPDATE SET label = EXCLUDED.label",
        code,
        label,
    )


async def _seed_dataset_version(
    conn: asyncpg.Connection,
    *,
    name: str,
    url: str,
    checksum: str,
    row_count: int = 100,
) -> None:
    await conn.execute(
        """
        INSERT INTO dataset_versions (name, url, checksum, etag, row_count, metadata)
        VALUES ($1, $2, $3, NULL, $4, '{}'::jsonb)
        """,
        name,
        url,
        checksum,
        row_count,
    )


# ---------------------------------------------------------------------------
# hazard_at
# ---------------------------------------------------------------------------
async def test_hazard_at_returns_class_for_point_inside_polygon(
    geodata_conn: asyncpg.Connection,
) -> None:
    await _seed_pai(
        geodata_conn,
        pai_id="PAI-PUG-1",
        hazard_class="P3",
        bbox=(16.80, 41.10, 16.90, 41.20),
        region="puglia",
    )
    # Point safely inside the seeded polygon.
    result = await hazard_at(geodata_conn, lat=41.15, lon=16.85)
    assert result["pai_class"] == "P3"
    assert result["pai_authority"] == "AdB-Test"
    assert result["region"] == "puglia"


async def test_hazard_at_picks_most_severe_when_overlapping(
    geodata_conn: asyncpg.Connection,
) -> None:
    """Two overlapping polygons — P4 must win over P1."""
    await _seed_pai(
        geodata_conn,
        pai_id="PAI-PUG-A",
        hazard_class="P1",
        bbox=(16.80, 41.10, 16.90, 41.20),
    )
    await _seed_pai(
        geodata_conn,
        pai_id="PAI-PUG-B",
        hazard_class="P4",
        bbox=(16.80, 41.10, 16.90, 41.20),
    )
    out = await hazard_at(geodata_conn, lat=41.15, lon=16.85)
    assert out["pai_class"] == "P4"


async def test_hazard_at_outside_polygons_returns_none(
    geodata_conn: asyncpg.Connection,
) -> None:
    await _seed_pai(
        geodata_conn,
        pai_id="PAI-far",
        hazard_class="P3",
        bbox=(16.80, 41.10, 16.90, 41.20),
    )
    # Point well outside the seeded polygon.
    out = await hazard_at(geodata_conn, lat=44.0, lon=11.0)
    assert out["pai_class"] is None


# ---------------------------------------------------------------------------
# iffi_query — Dizionario JOIN decodes attributes
# ---------------------------------------------------------------------------
async def test_iffi_query_decodes_movement_via_lookup(
    geodata_conn: asyncpg.Connection,
) -> None:
    await _seed_dizionario(geodata_conn, code="FRA-001", label="Scivolamento rotazionale")
    await _seed_iffi(
        geodata_conn,
        iffi_id="I-1",
        region="puglia",
        geom_type="piff_poly",
        movement_type="FRA-001",
        point=(16.85, 41.15),
    )
    out = await iffi_query(geodata_conn, region="puglia", limit=10)
    assert len(out) == 1
    assert out[0]["movement_type"] == "FRA-001"
    assert out[0]["movement_label"] == "Scivolamento rotazionale"
    assert out[0]["id"] == "puglia|I-1|piff_poly"


async def test_iffi_query_filters_by_bbox(
    geodata_conn: asyncpg.Connection,
) -> None:
    await _seed_iffi(
        geodata_conn,
        iffi_id="INSIDE",
        region="puglia",
        geom_type="piff_poly",
        movement_type=None,
        point=(16.85, 41.15),
    )
    await _seed_iffi(
        geodata_conn,
        iffi_id="OUTSIDE",
        region="puglia",
        geom_type="piff_poly",
        movement_type=None,
        point=(20.00, 41.15),
    )
    out = await iffi_query(
        geodata_conn,
        bbox=(16.80, 41.10, 16.90, 41.20),
        limit=10,
    )
    ids = {row["iffi_id"] for row in out}
    assert ids == {"INSIDE"}


async def test_iffi_query_filter_by_movement_type(
    geodata_conn: asyncpg.Connection,
) -> None:
    await _seed_dizionario(geodata_conn, code="A", label="Tipo A")
    await _seed_dizionario(geodata_conn, code="B", label="Tipo B")
    await _seed_iffi(
        geodata_conn,
        iffi_id="I-A",
        region="puglia",
        geom_type="piff_poly",
        movement_type="A",
        point=(16.85, 41.15),
    )
    await _seed_iffi(
        geodata_conn,
        iffi_id="I-B",
        region="puglia",
        geom_type="piff_poly",
        movement_type="B",
        point=(16.87, 41.17),
    )
    out = await iffi_query(geodata_conn, region="puglia", movement_type="A", limit=10)
    assert {r["iffi_id"] for r in out} == {"I-A"}
    assert out[0]["movement_label"] == "Tipo A"


async def test_iffi_query_respects_limit(
    geodata_conn: asyncpg.Connection,
) -> None:
    for i in range(5):
        await _seed_iffi(
            geodata_conn,
            iffi_id=f"I-{i}",
            region="puglia",
            geom_type="piff_poly",
            movement_type=None,
            point=(16.85 + i * 0.001, 41.15),
        )
    out = await iffi_query(geodata_conn, region="puglia", limit=3)
    assert len(out) == 3


# ---------------------------------------------------------------------------
# pai_summary — per-class area + count
# ---------------------------------------------------------------------------
async def test_pai_summary_aggregates_by_class(
    geodata_conn: asyncpg.Connection,
) -> None:
    await _seed_pai(geodata_conn, pai_id="A1", hazard_class="AA", bbox=(16.80, 41.10, 16.81, 41.11))
    await _seed_pai(geodata_conn, pai_id="A2", hazard_class="AA", bbox=(16.82, 41.10, 16.83, 41.11))
    await _seed_pai(
        geodata_conn, pai_id="P3-1", hazard_class="P3", bbox=(16.85, 41.15, 16.86, 41.16)
    )
    out = await pai_summary(geodata_conn)
    by_class = {row["hazard_class"]: row for row in out}
    assert by_class["AA"]["feature_count"] == 2
    assert by_class["P3"]["feature_count"] == 1
    # Geodesic area must be a positive km² figure, not 0.
    assert by_class["AA"]["area_km2"] > 0
    assert by_class["P3"]["area_km2"] > 0


async def test_pai_summary_region_filter(
    geodata_conn: asyncpg.Connection,
) -> None:
    await _seed_pai(
        geodata_conn,
        pai_id="P-pug",
        hazard_class="P3",
        bbox=(16.80, 41.10, 16.81, 41.11),
        region="puglia",
    )
    await _seed_pai(
        geodata_conn,
        pai_id="P-bas",
        hazard_class="P3",
        bbox=(16.00, 40.00, 16.01, 40.01),
        region="basilicata",
    )
    out = await pai_summary(geodata_conn, region="puglia")
    assert len(out) == 1
    assert out[0]["feature_count"] == 1


# ---------------------------------------------------------------------------
# dataset_status — latest row per name
# ---------------------------------------------------------------------------
async def test_dataset_status_returns_latest_version_per_name(
    geodata_conn: asyncpg.Connection,
) -> None:
    import asyncio

    await _seed_dataset_version(
        geodata_conn,
        name="pai_frane",
        url="https://idrogeo.isprambiente.it/old.zip",
        checksum="a" * 64,
        row_count=900_000,
    )
    # Same name, newer checksum — must shadow the older one.
    await asyncio.sleep(0.05)
    await _seed_dataset_version(
        geodata_conn,
        name="pai_frane",
        url="https://idrogeo.isprambiente.it/new.zip",
        checksum="b" * 64,
        row_count=920_000,
    )
    await _seed_dataset_version(
        geodata_conn,
        name="iffi_puglia_piff_poly",
        url="https://idrogeo.isprambiente.it/iffi.zip",
        checksum="c" * 64,
        row_count=1234,
    )
    out = await dataset_status(geodata_conn)
    by_name = {row["name"]: row for row in out}
    assert set(by_name) == {"pai_frane", "iffi_puglia_piff_poly"}
    # The latest pai_frane (newer fetched_at) must be the one returned.
    assert by_name["pai_frane"]["checksum"] == "b" * 64
    assert by_name["pai_frane"]["row_count"] == 920_000


# ---------------------------------------------------------------------------
# refresh — admin token guard
# ---------------------------------------------------------------------------
async def test_refresh_denies_without_admin_token(
    geodata_conn: asyncpg.Connection,
) -> None:
    """refresh() MUST fail-closed when MCP_ADMIN_TOKEN is unset.

    Per project doc: the env var unset disables refresh entirely, which is
    safer than silently allowing it.
    """
    saved = os.environ.pop(MCP_ADMIN_TOKEN_ENV, None)
    try:
        with pytest.raises(RefreshAuthError):
            await refresh(dataset="pai_frane", admin_token=None)
        with pytest.raises(RefreshAuthError):
            await refresh(dataset="pai_frane", admin_token="anything")
    finally:
        if saved is not None:
            os.environ[MCP_ADMIN_TOKEN_ENV] = saved


async def test_refresh_denies_wrong_token(geodata_conn: asyncpg.Connection) -> None:
    with (
        patch.dict(os.environ, {MCP_ADMIN_TOKEN_ENV: "supersecret"}),
        pytest.raises(RefreshAuthError),
    ):
        await refresh(dataset="pai_frane", admin_token="not-the-right-one")


async def test_refresh_runs_pipeline_with_valid_token(
    geodata_conn: asyncpg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid token triggers the init pipeline for the named dataset.

    We stub the pipeline so the test stays offline — the assertion is
    that the token check passes and `run_init_pipeline` is invoked with
    the expected ``only=dataset, force=True`` arguments.
    """
    calls: list[dict[str, Any]] = []

    async def _fake_pipeline(**kwargs: Any) -> int:
        calls.append(kwargs)
        return 0

    monkeypatch.setattr("geodata.init.runner.run_init_pipeline", _fake_pipeline)

    with patch.dict(os.environ, {MCP_ADMIN_TOKEN_ENV: "supersecret"}):
        out = await refresh(dataset="pai_frane", admin_token="supersecret")

    assert out == {"dataset": "pai_frane", "exit_code": 0}
    assert len(calls) == 1
    assert calls[0]["only"] == "pai_frane"
    assert calls[0]["force"] is True
