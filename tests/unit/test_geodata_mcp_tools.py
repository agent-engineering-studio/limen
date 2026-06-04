"""Geo-Data Service — MCP tool input validation + admin-token gate."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

import pytest

from geodata.mcp.tools import (
    MCP_ADMIN_TOKEN_ENV,
    RefreshAuthError,
    _admin_token_matches,
    hazard_at,
    iffi_query,
    pai_summary,
    refresh,
)


# ---------------------------------------------------------------------------
# Fake DB connection — captures the SQL + params so we can assert on shape
# ---------------------------------------------------------------------------
class _FakeConn:
    def __init__(self, *, fetchrow_return: Any = None, fetch_return: list[Any] | None = None):
        self.fetchrow_return = fetchrow_return
        self.fetch_return = fetch_return or []
        self.last_sql: str | None = None
        self.last_params: tuple[Any, ...] = ()

    async def fetchrow(self, sql: str, *params: Any) -> Any:
        self.last_sql = sql
        self.last_params = params
        return self.fetchrow_return

    async def fetch(self, sql: str, *params: Any) -> list[Any]:
        self.last_sql = sql
        self.last_params = params
        return self.fetch_return


# ---------------------------------------------------------------------------
# hazard_at
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_hazard_at_rejects_out_of_range_lat() -> None:
    with pytest.raises(ValueError, match="out of range"):
        await hazard_at(_FakeConn(), lat=99.0, lon=10.0)


@pytest.mark.asyncio
async def test_hazard_at_rejects_out_of_range_lon() -> None:
    with pytest.raises(ValueError, match="out of range"):
        await hazard_at(_FakeConn(), lat=41.0, lon=200.0)


@pytest.mark.asyncio
async def test_hazard_at_passes_lon_lat_in_that_order() -> None:
    # PostGIS ST_MakePoint takes (x=lon, y=lat). Easy to swap by accident.
    conn = _FakeConn(
        fetchrow_return={"hazard_class": "P3", "authority": "AdB Puglia", "region": "puglia"}
    )
    out = await hazard_at(conn, lat=41.12, lon=16.86)
    assert conn.last_params == (16.86, 41.12)
    assert out["pai_class"] == "P3"
    assert out["region"] == "puglia"


@pytest.mark.asyncio
async def test_hazard_at_returns_none_when_no_intersect() -> None:
    conn = _FakeConn(fetchrow_return=None)
    out = await hazard_at(conn, lat=41.12, lon=16.86)
    assert out["pai_class"] is None
    assert out["pai_authority"] is None


# ---------------------------------------------------------------------------
# iffi_query — argument validation + SQL shape
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_iffi_query_rejects_invalid_limit() -> None:
    with pytest.raises(ValueError, match="limit"):
        await iffi_query(_FakeConn(), region="puglia", limit=0)
    with pytest.raises(ValueError, match="limit"):
        await iffi_query(_FakeConn(), region="puglia", limit=1000)


@pytest.mark.asyncio
async def test_iffi_query_requires_filter() -> None:
    with pytest.raises(ValueError, match="bbox or region"):
        await iffi_query(_FakeConn())


@pytest.mark.asyncio
async def test_iffi_query_normalises_region_to_lowercase() -> None:
    conn = _FakeConn(fetch_return=[])
    await iffi_query(conn, region="PUGLIA", limit=10)
    # The first param is region (no bbox in this call).
    assert conn.last_params[0] == "puglia"


@pytest.mark.asyncio
async def test_iffi_query_joins_dizionario() -> None:
    conn = _FakeConn(fetch_return=[])
    await iffi_query(conn, region="puglia", limit=10)
    assert conn.last_sql is not None
    assert "iffi_lookup_movements" in conn.last_sql
    assert "movement_label" in conn.last_sql


@pytest.mark.asyncio
async def test_iffi_query_decodes_attributes() -> None:
    conn = _FakeConn(
        fetch_return=[
            {
                "id": "puglia|123|piff_poly",
                "iffi_id": "123",
                "region": "puglia",
                "geom_type": "piff_poly",
                "movement_type": "FRA-001",
                "movement_label": "Scivolamento rotazionale",
                "state": "attivo",
                "velocity_class": "lenta",
                "occurrence_date": None,
            }
        ]
    )
    out = await iffi_query(conn, region="puglia", limit=10)
    assert out[0]["movement_label"] == "Scivolamento rotazionale"


# ---------------------------------------------------------------------------
# pai_summary
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_pai_summary_no_filter_returns_full_distribution() -> None:
    conn = _FakeConn(
        fetch_return=[
            {"hazard_class": "AA", "feature_count": 1000, "area_km2": 12.5},
            {"hazard_class": "P4", "feature_count": 25, "area_km2": 0.4},
        ]
    )
    out = await pai_summary(conn)
    assert len(out) == 2
    assert {row["hazard_class"] for row in out} == {"AA", "P4"}


@pytest.mark.asyncio
async def test_pai_summary_region_filter_emits_clause() -> None:
    conn = _FakeConn(fetch_return=[])
    await pai_summary(conn, region="puglia")
    assert "p.region = $1" in (conn.last_sql or "")
    assert conn.last_params == ("puglia",)


# ---------------------------------------------------------------------------
# refresh — admin token gate
# ---------------------------------------------------------------------------
def test_admin_token_matches_only_when_env_set_and_provided() -> None:
    with patch.dict(os.environ, {MCP_ADMIN_TOKEN_ENV: "supersecret"}):
        assert _admin_token_matches("supersecret") is True
        assert _admin_token_matches("wrong") is False
        assert _admin_token_matches(None) is False


def test_admin_token_matches_returns_false_when_env_unset() -> None:
    # No env var configured → refresh is effectively disabled.
    saved = os.environ.pop(MCP_ADMIN_TOKEN_ENV, None)
    try:
        assert _admin_token_matches("anything") is False
    finally:
        if saved is not None:
            os.environ[MCP_ADMIN_TOKEN_ENV] = saved


@pytest.mark.asyncio
async def test_refresh_raises_without_valid_token() -> None:
    with patch.dict(os.environ, {MCP_ADMIN_TOKEN_ENV: "supersecret"}):
        with pytest.raises(RefreshAuthError):
            await refresh(dataset="pai_frane", admin_token=None)
        with pytest.raises(RefreshAuthError):
            await refresh(dataset="pai_frane", admin_token="wrong")
