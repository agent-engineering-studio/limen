from limen.core.models.risk import RiskLevel
from limen.report.render import ClusterView, ReportView, render_html


def _view() -> ReportView:
    return ReportView(
        title="Limen — Zone a rischio",
        valuation_time="2026-07-11T08:00:00Z",
        pipeline_version="v1",
        national_summary="Quadro nazionale di prova.",
        clusters=[
            ClusterView(
                cluster_id=0,
                aoi_id="puglia",
                level=RiskLevel.VeryHigh,
                level_label="Molto alto",
                level_color="#bd0026",
                max_score=0.91,
                n_cells=4,
                image_rel="assets/cluster-0.png",
                reason="Il punteggio nasce soprattutto dalla pioggia.",
                verdict_text="Da attenzionare: rischio alto.",
                verdict_tone="warn",
                components=[("Versante", 0.5, "#8c6d31"), ("Pioggia", 0.8, "#1f77b4")],
            )
        ],
    )


def test_render_produces_html_with_cluster_and_palette() -> None:
    html = render_html(_view())
    assert "<!doctype html>" in html.lower() or "<html" in html.lower()
    assert "assets/cluster-0.png" in html
    assert "#bd0026" in html
    assert "Molto alto" in html
    assert "Da attenzionare" in html


def test_render_escapes_text() -> None:
    view = _view()
    view.national_summary = "<script>alert(1)</script>"
    html = render_html(view)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
