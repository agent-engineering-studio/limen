"""limen-ops MCP: admin gate is fail-closed (pure, no DB)."""

from __future__ import annotations

import pytest

from limen.mcp.tools import (
    ADMIN_TOKEN_ENV,
    AdminAuthError,
    build_static_report,
    check_admin_token,
    run_forecast_history,
)


def test_gate_fail_closed_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ADMIN_TOKEN_ENV, raising=False)
    with pytest.raises(AdminAuthError):
        check_admin_token("anything")


async def test_report_tools_are_admin_gated(monkeypatch: pytest.MonkeyPatch) -> None:
    # Fail-closed: no admin token env ⇒ the mutating report tools refuse before
    # touching the DB / building anything.
    monkeypatch.delenv(ADMIN_TOKEN_ENV, raising=False)
    with pytest.raises(AdminAuthError):
        await build_static_report(admin_token=None)
    with pytest.raises(AdminAuthError):
        await run_forecast_history(admin_token="x")


def test_gate_rejects_wrong_and_missing_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ADMIN_TOKEN_ENV, "s3cret")
    with pytest.raises(AdminAuthError):
        check_admin_token("wrong")
    with pytest.raises(AdminAuthError):
        check_admin_token(None)
    check_admin_token("s3cret")  # non deve sollevare
