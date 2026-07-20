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

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from limen.core.logging import get_logger
from limen.data.db import acquire, lifespan_pool
from limen.data.migrate import run_migrations
from limen.ml.shadow import (
    DEFAULT_SINCE as _DEFAULT_SINCE,
)
from limen.ml.shadow import (
    AoiShadowStats,
    collect_shadow_summary,
)

log = get_logger(__name__)

REPORTS_DIR = Path("./reports")


def _write_report(
    *,
    since: datetime,
    aoi_filter: str | None,
    stats: list[AoiShadowStats],
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
    try:
        since = datetime.fromisoformat(raw_since) if raw_since else _DEFAULT_SINCE
    except ValueError:
        log.error(
            "shadow_report.bad_since",
            value=raw_since,
            hint="ISO 8601, es. 2026-07-06T13:00:00+00:00",
        )
        return 1
    if since.tzinfo is None:
        since = since.replace(tzinfo=UTC)
    aoi_filter = os.getenv("LIMEN_SHADOW_AOI") or None

    async with lifespan_pool():
        await run_migrations()
        async with acquire() as conn:
            summary = await collect_shadow_summary(
                conn, since=since, aoi_filter=aoi_filter, with_top=True
            )

    report = _write_report(
        since=summary.since,
        aoi_filter=summary.aoi_filter,
        stats=summary.stats,
        truth_rows=summary.truth_rows,
        model_versions=summary.model_versions,
    )
    log.info(
        "shadow_report.done",
        since=since.isoformat(),
        paired_runs=summary.total_pairs,
        aois=len(summary.stats),
        truth_events=len(summary.truth_rows),
        report=str(report),
    )
    return 0


def main() -> int:
    import asyncio

    return asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
