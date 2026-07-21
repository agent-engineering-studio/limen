"""Rendering HTML del report con Jinja2 (autoescape attivo)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from limen.core.models.risk import RiskLevel
from limen.report.palette import RISK_CLASSES

if TYPE_CHECKING:
    from jinja2 import Environment

_env: Environment | None = None


def _get_env() -> Environment:
    global _env
    if _env is None:
        from jinja2 import Environment, PackageLoader, select_autoescape

        _env = Environment(
            loader=PackageLoader("limen.report", "templates"),
            autoescape=select_autoescape(["html", "j2"]),
        )
    return _env


@dataclass
class ClusterView:
    cluster_id: int
    aoi_id: str
    level: RiskLevel
    level_label: str
    level_color: str
    max_score: float
    n_cells: int
    map_id: str
    geojson: str
    center_lat: float
    center_lon: float
    coord_label: str
    reason: str
    verdict_text: str
    verdict_tone: str
    components: list[tuple[str, float, str]]
    # Inline SVG sparkline (observed 72h + forecast 72h). "" when no history.
    trend_svg: str = ""


@dataclass
class ReportView:
    title: str
    valuation_time: str
    pipeline_version: str
    national_summary: str
    basemap_url: str
    basemap_attribution: str
    clusters: list[ClusterView] = field(default_factory=list)
    # Informational banner (e.g. "zones shown are below the alert threshold").
    notice: str | None = None
    # Administrative rollup: comuni with alerting cells (exposure-ranked).
    top_comuni: list[dict[str, object]] = field(default_factory=list)


def render_html(view: ReportView) -> str:
    template = _get_env().get_template("report.html.j2")
    return template.render(view=view, classes=RISK_CLASSES)
