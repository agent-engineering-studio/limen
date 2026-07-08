"""``limen shadow-report`` — champion vs ML-challenger comparison (issue #4).

Reads ``model_runs`` (role=challenger) directly instead of
``v_shadow_comparison``: the view keeps only the latest run per cell,
while the verdict needs the whole observation window. Each challenger
run is paired with the champion assessment of the same cell closest in
time (within 1 h).

Env knobs:

* ``LIMEN_SHADOW_SINCE`` — ISO datetime cutoff. Defaults to
  2026-07-06T13:00Z: earlier rows have the ML probabilities computed
  with the rain features stuck at zero (bug fixed in 7d19fe4) and must
  not be judged.
* ``LIMEN_SHADOW_AOI``   — restrict to one AOI (default: all).

The report never promotes anything: promotion stays a manual
``mlflow models transition-stage`` call (locked invariant).
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from limen.core.logging import get_logger
from limen.data.db import acquire, lifespan_pool
from limen.data.migrate import run_migrations

log = get_logger(__name__)

REPORTS_DIR = Path("./reports")
# Rows before this instant carry rain features frozen at zero (fixed in
# 7d19fe4) — judging them would smear the verdict.
_DEFAULT_SINCE = datetime(2026, 7, 6, 13, 0, tzinfo=UTC)

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

# Dated landslide events (ITALICA) in the window, mapped to cells; for
# each, the last run of both engines before the event (48 h lookback).
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


@dataclass(frozen=True, slots=True)
class _AoiStats:
    aoi_id: str
    n: int
    mean_abs_div: float
    p95_abs_div: float
    max_abs_div: float
    correlation: float | None
    class_agreement: float
    top_divergent: list[tuple[str, float, float, float]]  # cell, champ, ml, div


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0.0 or vy == 0.0:
        return None
    return cov / math.sqrt(vx * vy)


def _percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, round(q * (len(sorted_values) - 1)))
    return sorted_values[idx]


def _aoi_stats(aoi_id: str, pairs: list[dict[str, Any]]) -> _AoiStats:
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
    return _AoiStats(
        aoi_id=aoi_id,
        n=len(pairs),
        mean_abs_div=sum(abs_sorted) / len(abs_sorted),
        p95_abs_div=_percentile(abs_sorted, 0.95),
        max_abs_div=abs_sorted[-1],
        correlation=_pearson(champs, mls),
        class_agreement=agree / len(pairs),
        top_divergent=top,
    )


def _write_report(
    *,
    since: datetime,
    aoi_filter: str | None,
    stats: list[_AoiStats],
    truth_rows: list[dict[str, Any]],
    model_versions: list[str],
) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"shadow_report_{since.date()}.md"
    lines = [
        "# Limen shadow report — champion (V1) vs challenger (ML)",
        "",
        f"Window: **{since.isoformat()} → now** (rows before the cutoff have",
        "the rain-features-at-zero bug, fix 7d19fe4, and are excluded).",
        f"Generated: {datetime.now(UTC).isoformat()}",
        f"AOI filter: `{aoi_filter or 'all'}` · challenger versions: "
        f"{', '.join(model_versions) or 'n/a'}",
        "",
        "## Divergence per AOI (divergence = ml_probability - champion_score)",
        "",
    ]
    if not stats:
        lines += [
            "_No challenger runs in the window — is shadow mode on and has",
            "the hourly job run since the cutoff?_",
            "",
        ]
    for s in stats:
        corr = f"{s.correlation:.3f}" if s.correlation is not None else "n/a"
        lines += [
            f"### `{s.aoi_id}` — {s.n} paired runs",
            "",
            f"- mean |div| **{s.mean_abs_div:.3f}** · p95 **{s.p95_abs_div:.3f}**"
            f" · max **{s.max_abs_div:.3f}**",
            f"- score correlation (Pearson): **{corr}**",
            f"- class agreement: **{s.class_agreement:.1%}**",
            "",
            "| cell | champion | ml | div |",
            "|------|----------|----|----|",
        ]
        lines += [
            f"| `{cell}` | {ch:.3f} | {ml:.3f} | {d:+.3f} |" for cell, ch, ml, d in s.top_divergent
        ]
        lines.append("")
    lines += ["## Ground truth — dated landslide events (ITALICA) in the window", ""]
    if not truth_rows:
        lines += [
            "_None. Expected with only days of data — re-run this command",
            "after 2-4 weeks of shadow observation (and re-ingest the ITALICA",
            "catalogue if a newer export covers the window)._",
            "",
        ]
    else:
        lines += [
            "| cell | aoi | event (UTC) | champion (pre) | ml (pre) |",
            "|------|-----|-------------|----------------|----------|",
        ]
        for r in truth_rows:
            ch = f"{float(r['champion_score']):.3f}" if r["champion_score"] is not None else "—"
            ml = f"{float(r['ml_probability']):.3f}" if r["ml_probability"] is not None else "—"
            lines.append(
                f"| `{r['cell_id']}` | {r['aoi_id']} | "
                f"{r['event_time'].isoformat()} | {ch} | {ml} |"
            )
        lines.append("")
    lines += [
        "## Verdict",
        "",
        "This report never promotes anything. If the challenger convinces",
        "over the full 2-4 week window, promotion is a **manual**",
        "`mlflow models transition-stage` call (and/or `SCORING__ENGINE=ml`).",
        "The drift monitor (PSI/KS on rain_72h_mm) is informative only.",
        "",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


async def run() -> int:
    """Build the shadow-comparison report for the post-fix window."""
    raw_since = os.getenv("LIMEN_SHADOW_SINCE")
    since = datetime.fromisoformat(raw_since) if raw_since else _DEFAULT_SINCE
    if since.tzinfo is None:
        since = since.replace(tzinfo=UTC)
    aoi_filter = os.getenv("LIMEN_SHADOW_AOI") or None

    async with lifespan_pool():
        await run_migrations()
        async with acquire() as conn:
            pairs = [dict(r) for r in await conn.fetch(_PAIRS_SQL, since, aoi_filter)]
            truth_rows = [dict(r) for r in await conn.fetch(_TRUTH_SQL, since, aoi_filter)]

    by_aoi: dict[str, list[dict[str, Any]]] = {}
    for p in pairs:
        by_aoi.setdefault(str(p["aoi_id"] or "unknown"), []).append(p)
    stats = [_aoi_stats(aoi_id, rows) for aoi_id, rows in sorted(by_aoi.items())]
    model_versions = sorted({str(p["model_version"]) for p in pairs})

    report = _write_report(
        since=since,
        aoi_filter=aoi_filter,
        stats=stats,
        truth_rows=truth_rows,
        model_versions=model_versions,
    )
    log.info(
        "shadow_report.done",
        since=since.isoformat(),
        paired_runs=len(pairs),
        aois=len(stats),
        truth_events=len(truth_rows),
        report=str(report),
    )
    return 0


def main() -> int:
    import asyncio

    return asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
