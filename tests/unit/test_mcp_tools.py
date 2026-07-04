"""limen-ops MCP: admin gate is fail-closed (pure, no DB)."""

from __future__ import annotations

import pytest

from limen.mcp.tools import ADMIN_TOKEN_ENV, AdminAuthError, check_admin_token


def test_gate_fail_closed_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ADMIN_TOKEN_ENV, raising=False)
    with pytest.raises(AdminAuthError):
        check_admin_token("anything")


def test_gate_rejects_wrong_and_missing_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ADMIN_TOKEN_ENV, "s3cret")
    with pytest.raises(AdminAuthError):
        check_admin_token("wrong")
    with pytest.raises(AdminAuthError):
        check_admin_token(None)
    check_admin_token("s3cret")  # non deve sollevare
