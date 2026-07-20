"""Shared champion-vs-challenger shadow aggregation (issue #4 / #26).

The CLI (``limen shadow-report``) and the API (``/api/shadow/summary``) both
build the same picture from ``model_runs`` (role=challenger) paired with the
champion ``risk_assessments``. The logic lives here once so the two surfaces
can never diverge.

Pure aggregation (:func:`pearson`, :func:`aoi_stats`) has no DB; the DB fetch
(:func:`collect_shadow_summary`) takes a live connection so the caller owns
the pool. Nothing here promotes anything — promotion stays a manual
``mlflow models transition-stage`` call (locked invariant).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

# Rows before this instant carry rain features frozen at zero (fixed in
# 7d19fe4) — judging them would smear the verdict.
DEFAULT_SINCE = datetime(2026, 7, 6, 13, 0, tzinfo=UTC)

_PAIRS_SQL = """
SELECT m.cell_id, m.aoi_id, m.computed_at, m.probability, m.risk_class,
       m.model_version,
       r.score AS champion_score, r.class AS champion_class
FROM model_runs m
JOIN LATERAL (
    SELECT ra.score, ra.class
    FROM risk_assessments ra
    WHERE ra.cell_id = m.cell_id
      AND ra.computed_at BETWEEN m.computed_at - interval '1 hour'
                             AND m.computed_at + interval '1 hour'
    ORDER BY abs(extract(epoch FROM ra.computed_at - m.computed_at))
    LIMIT 1
) r ON true
WHERE m.role = 'challenger'
  AND m.computed_at >= $1
  AND ($2::text IS NULL OR m.aoi_id = $2)
"""

# Dated landslide events (ITALICA) in the window, mapped to cells; for each,
# the last run of both engines before the event (48 h lookback).
_TRUTH_SQL = """
WITH events AS (
    SELECT g.id AS cell_id, g.aoi_id, MIN(e.event_time) AS event_time
    FROM landslide_events e
    JOIN grid_cells g ON ST_Intersects(g.geom, e.geom)
    WHERE e.event_time >= $1
      AND ($2::text IS NULL OR g.aoi_id = $2)
    GROUP BY g.id, g.aoi_id
)
SELECT ev.cell_id, ev.aoi_id, ev.event_time,
       (SELECT m.probability FROM model_runs m
        WHERE m.cell_id = ev.cell_id AND m.role = 'challenger'
          AND m.computed_at BETWEEN ev.event_time - interval '48 hours'
                                AND ev.event_time
        ORDER BY m.computed_at DESC LIMIT 1) AS ml_probability,
       (SELECT ra.score FROM risk_assessments ra
        WHERE ra.cell_id = ev.cell_id
          AND ra.computed_at BETWEEN ev.event_time - interval '48 hours'
                                 AND ev.event_time
        ORDER BY ra.computed_at DESC LIMIT 1) AS champion_score
FROM events ev
ORDER BY ev.event_time
"""


class _Conn(Protocol):
    async def fetch(self, query: str, *args: Any) -> list[Any]: ...


@dataclass(frozen=True, slots=True)
class AoiShadowStats:
    aoi_id: str
    n: int
    mean_abs_div: float
    p95_abs_div: float
    max_abs_div: float
    correlation: float | None
    class_agreement: float
    top_divergent: list[tuple[str, float, float, float]]  # cell, champ, ml, div


@dataclass(frozen=True, slots=True)
class ShadowSummary:
    since: datetime
    aoi_filter: str | None
    stats: list[AoiShadowStats]
    truth_rows: list[dict[str, Any]]
    model_versions: list[str]
    total_pairs: int


def pearson(xs: list[float], ys: list[float]) -> float | None:
    try:
        return statistics.correlation(xs, ys)
    except statistics.StatisticsError:
        # meno di 2 punti o input costante
        return None


def _percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, round(q * (len(sorted_values) - 1)))
    return sorted_values[idx]


def aoi_stats(aoi_id: str, pairs: list[dict[str, Any]]) -> AoiShadowStats:
    champs = [float(p["champion_score"]) for p in pairs]
    mls = [float(p["probability"]) for p in pairs]
    divs = [ml - ch for ch, ml in zip(champs, mls, strict=True)]
    abs_sorted = sorted(abs(d) for d in divs)
    agree = sum(1 for p in pairs if p["risk_class"] == p["champion_class"])
    by_div = sorted(zip(pairs, divs, strict=True), key=lambda t: abs(t[1]), reverse=True)
    top = [
        (str(p["cell_id"]), float(p["champion_score"]), float(p["probability"]), d)
        for p, d in by_div[:10]
    ]
    return AoiShadowStats(
        aoi_id=aoi_id,
        n=len(pairs),
        mean_abs_div=sum(abs_sorted) / len(abs_sorted),
        p95_abs_div=_percentile(abs_sorted, 0.95),
        max_abs_div=abs_sorted[-1],
        correlation=pearson(champs, mls),
        class_agreement=agree / len(pairs),
        top_divergent=top,
    )


async def collect_shadow_summary(
    conn: _Conn, *, since: datetime, aoi_filter: str | None
) -> ShadowSummary:
    """Fetch + aggregate the post-fix shadow window from an open connection."""
    pairs = [dict(r) for r in await conn.fetch(_PAIRS_SQL, since, aoi_filter)]
    truth_rows = [dict(r) for r in await conn.fetch(_TRUTH_SQL, since, aoi_filter)]

    by_aoi: dict[str, list[dict[str, Any]]] = {}
    for p in pairs:
        by_aoi.setdefault(str(p["aoi_id"] or "unknown"), []).append(p)
    stats = [aoi_stats(aoi_id, rows) for aoi_id, rows in sorted(by_aoi.items())]
    model_versions = sorted({str(p["model_version"]) for p in pairs})
    return ShadowSummary(
        since=since,
        aoi_filter=aoi_filter,
        stats=stats,
        truth_rows=truth_rows,
        model_versions=model_versions,
        total_pairs=len(pairs),
    )
