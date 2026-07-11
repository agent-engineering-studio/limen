"""Job APScheduler per il report HTML statico: degrada, non solleva mai."""

from __future__ import annotations

import pytest

from limen.api.jobs.html_report import run_html_report


class _Deps:
    # build_report is monkeypatched, so the job never touches deps.settings'
    # contents — a bare marker object is all the stub needs to expose.
    settings = object()


async def test_job_swallows_errors_and_returns_status(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _boom(settings=None):  # type: ignore[no-untyped-def]
        raise RuntimeError("db down")

    monkeypatch.setattr("limen.api.jobs.html_report.build_report", _boom)
    result = await run_html_report(_Deps())  # must NOT raise
    assert result["ok"] is False


async def test_job_reports_built_path(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    async def _ok(settings=None):  # type: ignore[no-untyped-def]
        return tmp_path / "archive" / "b0"

    monkeypatch.setattr("limen.api.jobs.html_report.build_report", _ok)
    result = await run_html_report(_Deps())
    assert result["ok"] is True
