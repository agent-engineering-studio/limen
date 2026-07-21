"""Per-zone risk trend for the static report (issue #42).

At build time we read the dominant cell's observed (past 72h) + forecast
(+24/48/72h) risk from ``risk_assessments`` and inline a small SVG sparkline in
the report — no runtime API, no JS. ``trend_svg`` is pure and unit-tested; the
DB read mirrors ``GET /api/cell/{id}/history`` (issue #41).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

_W = 280
_H = 48
_PAD = 4

_OBSERVED_SQL = """
SELECT computed_at, score
FROM risk_assessments
WHERE cell_id = $1
  AND horizon NOT LIKE '+%'
  AND computed_at >= now() - make_interval(hours => $2::int)
ORDER BY computed_at
"""

_FORECAST_SQL = """
SELECT computed_at, horizon, score
FROM risk_assessments
WHERE cell_id = $1 AND pipeline_version LIKE 'v1-forecast+%'
ORDER BY horizon
"""

TrendPoint = tuple[datetime, float]


def trend_svg(observed: list[TrendPoint], forecast: list[TrendPoint]) -> str:
    """Inline SVG sparkline: observed (solid) + forecast (dashed) + now marker.

    Pure. Returns "" when there is nothing to draw (the template then omits it).
    """
    pts = observed + forecast
    if not pts:
        return ""
    times = [t.timestamp() for t, _ in pts]
    t0, t1 = min(times), max(times)
    span = (t1 - t0) or 1.0

    def sx(ts: float) -> float:
        return _PAD + (ts - t0) / span * (_W - 2 * _PAD)

    def sy(score: float) -> float:
        return _PAD + (1 - min(1.0, max(0.0, score))) * (_H - 2 * _PAD)

    def path(series: list[TrendPoint]) -> str:
        return " ".join(
            f"{'M' if i == 0 else 'L'}{sx(t.timestamp()):.1f},{sy(s):.1f}"
            for i, (t, s) in enumerate(series)
        )

    now_ts = (observed[-1][0] if observed else forecast[0][0]).timestamp()
    now_x = sx(now_ts)
    parts = [
        f'<svg class="zone-trend" viewBox="0 0 {_W} {_H}" role="img" '
        f'aria-label="andamento del rischio: passato 72h e previsione 72h">',
        f'<line x1="{now_x:.1f}" y1="0" x2="{now_x:.1f}" y2="{_H}" '
        f'stroke="#c3c7cf" stroke-dasharray="2 2"/>',
    ]
    if observed:
        parts.append(
            f'<path d="{path(observed)}" fill="none" stroke="#5e6473" stroke-width="1.5"/>'
        )
    if forecast:
        parts.append(
            f'<path d="{path(forecast)}" fill="none" stroke="#1f77b4" '
            f'stroke-width="1.5" stroke-dasharray="3 2"/>'
        )
    parts.append("</svg>")
    return "".join(parts)


def trend_points(observed: list[TrendPoint], forecast: list[TrendPoint]) -> dict[str, Any]:
    """Serialisable trend for the manifest (fact-checking archive)."""
    return {
        "observed": [[t.isoformat(), round(s, 6)] for t, s in observed],
        "forecast": [[t.isoformat(), round(s, 6)] for t, s in forecast],
    }


async def read_cell_trend(
    conn: Any, cell_id: str, *, hours: int = 72
) -> tuple[list[TrendPoint], list[TrendPoint]]:
    """Observed (past ``hours``) + forecast (target time) for a cell."""
    obs = [
        (r["computed_at"], float(r["score"]))
        for r in await conn.fetch(_OBSERVED_SQL, cell_id, hours)
    ]
    forecast: list[TrendPoint] = []
    for r in await conn.fetch(_FORECAST_SQL, cell_id):
        offset_h = int(str(r["horizon"]).lstrip("+").rstrip("h") or 0)
        forecast.append((r["computed_at"] + timedelta(hours=offset_h), float(r["score"])))
    forecast.sort(key=lambda p: p[0])
    return obs, forecast
