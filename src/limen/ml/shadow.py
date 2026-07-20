"""Shared champion-vs-challenger shadow aggregation (issue #4 / #26).

The CLI (``limen shadow-report``) and the API (``/api/shadow/summary``) both
build the same picture from ``model_runs`` (role=challenger) paired with the
champion ``risk_assessments``. The logic lives here once so the two surfaces
can never diverge.

The aggregation runs **in SQL** (``avg``/``corr``/``percentile_cont`` grouped
by AOI): the national window is ~1.6M paired runs — collapsing to ~20 AOI rows
in the DB is seconds, whereas pulling every pair to Python timed out. The
per-cell divergence pairing is a nearest-in-time LATERAL join (±1 h) indexed by
``(cell_id, computed_at)``. Nothing here promotes anything — promotion stays a
manual ``mlflow models transition-stage`` call (locked invariant).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

# Rows before this instant carry rain features frozen at zero (fixed in
# 7d19fe4) — judging them would smear the verdict.
DEFAULT_SINCE = datetime(2026, 7, 6, 13, 0, tzinfo=UTC)

# Per-cell champion pairing: the assessment nearest in time (±1 h) to each
# challenger run. Shared by the aggregate and top-divergent queries.
_PAIR_LATERAL = """
FROM model_runs m
JOIN aoi a ON a.id = m.aoi_id
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

# Per-AOI aggregates over the whole window (divergence = ml_probability -
# champion_score). corr() is NULL for <2 rows or zero variance.
_STATS_SQL = f"""
SELECT m.aoi_id                                                        AS aoi_id,
       max(a.name)                                                     AS aoi_name,
       count(*)                                                        AS n,
       avg(abs(m.probability - r.score))                              AS mean_abs_div,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY abs(m.probability - r.score))
                                                                       AS p95_abs_div,
       max(abs(m.probability - r.score))                              AS max_abs_div,
       corr(r.score, m.probability)                                   AS correlation,
       avg(CASE WHEN m.risk_class = r.class THEN 1.0 ELSE 0.0 END)    AS class_agreement
{_PAIR_LATERAL}
GROUP BY m.aoi_id
ORDER BY m.aoi_id
"""

# Top-10 most-divergent cells per AOI (CLI report only — a second LATERAL scan).
_TOP_SQL = f"""
SELECT aoi_id, cell_id, champion_score, ml_probability, divergence
FROM (
    SELECT m.aoi_id                    AS aoi_id,
           m.cell_id                   AS cell_id,
           r.score                     AS champion_score,
           m.probability               AS ml_probability,
           m.probability - r.score     AS divergence,
           row_number() OVER (
               PARTITION BY m.aoi_id ORDER BY abs(m.probability - r.score) DESC, m.cell_id
           ) AS rn
    {_PAIR_LATERAL}
) t
WHERE rn <= 10
ORDER BY aoi_id, rn
"""

_VERSIONS_SQL = """
SELECT DISTINCT model_version
FROM model_runs
WHERE role = 'challenger'
  AND computed_at >= $1
  AND ($2::text IS NULL OR aoi_id = $2)
ORDER BY model_version
"""

# Dated landslide events (ITALICA) in the window, mapped to cells; for each,
# the last run of both engines before the event (48 h lookback).
_TRUTH_SQL = """
WITH events AS (
    SELECT g.id AS cell_id, g.aoi_id, max(a.name) AS aoi_name,
           MIN(e.event_time) AS event_time
    FROM landslide_events e
    JOIN grid_cells g ON ST_Intersects(g.geom, e.geom)
    JOIN aoi a ON a.id = g.aoi_id
    WHERE e.event_time >= $1
      AND ($2::text IS NULL OR g.aoi_id = $2)
    GROUP BY g.id, g.aoi_id
)
SELECT ev.cell_id, ev.aoi_id, ev.aoi_name, ev.event_time,
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
    aoi_name: str
    n: int
    mean_abs_div: float
    p95_abs_div: float
    max_abs_div: float
    correlation: float | None
    class_agreement: float
    # cell, champion_score, ml_probability, divergence — CLI report only.
    top_divergent: list[tuple[str, float, float, float]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ShadowSummary:
    since: datetime
    aoi_filter: str | None
    stats: list[AoiShadowStats]
    truth_rows: list[dict[str, Any]]
    model_versions: list[str]
    total_pairs: int


async def collect_shadow_summary(
    conn: _Conn, *, since: datetime, aoi_filter: str | None, with_top: bool = False
) -> ShadowSummary:
    """Aggregate the post-fix shadow window per AOI from an open connection.

    ``with_top`` runs a second LATERAL scan for the top-10 divergent cells per
    AOI (the CLI report); the API leaves it off to answer in a single scan.
    """
    stat_rows = await conn.fetch(_STATS_SQL, since, aoi_filter)
    truth_rows = [dict(r) for r in await conn.fetch(_TRUTH_SQL, since, aoi_filter)]
    versions = await conn.fetch(_VERSIONS_SQL, since, aoi_filter)

    top_by_aoi: dict[str, list[tuple[str, float, float, float]]] = {}
    if with_top:
        for t in await conn.fetch(_TOP_SQL, since, aoi_filter):
            top_by_aoi.setdefault(str(t["aoi_id"]), []).append(
                (
                    str(t["cell_id"]),
                    float(t["champion_score"]),
                    float(t["ml_probability"]),
                    float(t["divergence"]),
                )
            )

    stats = [
        AoiShadowStats(
            aoi_id=str(r["aoi_id"]),
            aoi_name=str(r["aoi_name"]),
            n=int(r["n"]),
            mean_abs_div=float(r["mean_abs_div"]),
            p95_abs_div=float(r["p95_abs_div"]),
            max_abs_div=float(r["max_abs_div"]),
            correlation=(float(r["correlation"]) if r["correlation"] is not None else None),
            class_agreement=float(r["class_agreement"]),
            top_divergent=top_by_aoi.get(str(r["aoi_id"]), []),
        )
        for r in stat_rows
    ]
    return ShadowSummary(
        since=since,
        aoi_filter=aoi_filter,
        stats=stats,
        truth_rows=truth_rows,
        model_versions=[str(v["model_version"]) for v in versions],
        total_pairs=sum(s.n for s in stats),
    )
