"""Static HTML report settings — pure unit tests."""

from __future__ import annotations

import pytest

from limen.config.settings import ReportSettings


def test_report_html_defaults() -> None:
    s = ReportSettings()
    assert s.html_enabled is True
    assert s.html_interval_hours == 1
    assert s.html_run_at_startup is True
    assert s.html_max_clusters == 50
    assert s.html_min_level.value == "High"
    assert s.html_publish is False


def test_report_html_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPORT__HTML_INTERVAL_HOURS", "6")
    monkeypatch.setenv("REPORT__HTML_ENABLED", "false")
    from limen.config.settings import Settings

    s = Settings().report
    assert s.html_interval_hours == 6
    assert s.html_enabled is False
