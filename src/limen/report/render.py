"""Rendering HTML del report con Jinja2 (autoescape attivo)."""

from __future__ import annotations

from dataclasses import dataclass, field

from jinja2 import Environment, PackageLoader, select_autoescape

from limen.core.models.risk import RiskLevel
from limen.report.palette import RISK_CLASSES

_env = Environment(
    loader=PackageLoader("limen.report", "templates"),
    autoescape=select_autoescape(["html", "j2"]),
)


@dataclass
class ClusterView:
    cluster_id: int
    aoi_id: str
    level: RiskLevel
    level_label: str
    level_color: str
    max_score: float
    n_cells: int
    image_rel: str
    reason: str
    verdict_text: str
    verdict_tone: str
    components: list[tuple[str, float, str]]


@dataclass
class ReportView:
    title: str
    valuation_time: str
    pipeline_version: str
    national_summary: str
    clusters: list[ClusterView] = field(default_factory=list)


def render_html(view: ReportView) -> str:
    template = _env.get_template("report.html.j2")
    return template.render(view=view, classes=RISK_CLASSES)
