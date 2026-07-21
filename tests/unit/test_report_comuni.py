"""Report renders the comuni section when data is present."""

from __future__ import annotations

from limen.report.render import ReportView, render_html


def test_comuni_section_rendered() -> None:
    view = ReportView(
        title="t",
        valuation_time="2026-07-21",
        pipeline_version="v1",
        national_summary="",
        basemap_url="",
        basemap_attribution="",
        top_comuni=[{"name": "Testville", "worst_class": "High", "n_alert": 3}],
    )
    html = render_html(view)
    assert "Comuni a maggior rischio" in html
    assert "Testville" in html


def test_comuni_section_absent_when_empty() -> None:
    view = ReportView(
        title="t",
        valuation_time="2026-07-21",
        pipeline_version="v1",
        national_summary="",
        basemap_url="",
        basemap_attribution="",
    )
    assert "Comuni a maggior rischio" not in render_html(view)
