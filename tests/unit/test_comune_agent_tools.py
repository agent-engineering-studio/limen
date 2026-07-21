"""Comune MCP tool bodies + A2A skill routing (repo stubbed, no DB)."""

from __future__ import annotations

from typing import Any

import pytest

from limen.a2a.models import DataPart, Message
from limen.a2a.skills import SKILLS, resolve_invocation
from limen.mcp import tools


@pytest.fixture(autouse=True)
def _stub(monkeypatch: pytest.MonkeyPatch) -> None:
    import limen.data.repos.comune_risk as cr

    async def _detail(code: str) -> dict[str, Any] | None:
        return {"comune": {"istat_code": code, "worst_class": "High"}, "cells": []}

    async def _top(*, aoi_id: str | None, limit: int) -> list[dict[str, Any]]:
        return [{"istat_code": "C001", "worst_class": "High"}]

    monkeypatch.setattr(cr, "comune_detail", _detail)
    monkeypatch.setattr(cr, "top_comuni", _top)


async def test_comune_risk_tool() -> None:
    assert (await tools.comune_risk("C001"))["worst_class"] == "High"


async def test_a2a_comune_skills_registered() -> None:
    assert "top_comuni" in SKILLS and "comune_risk" in SKILLS
    msg = Message(
        role="user",
        message_id="m1",
        parts=[DataPart(data={"skill": "comune_risk", "params": {"istat_code": "C001"}})],
    )
    skill_id, params = resolve_invocation(msg)
    assert skill_id == "comune_risk"
    assert (await SKILLS[skill_id].handler(params))["worst_class"] == "High"
