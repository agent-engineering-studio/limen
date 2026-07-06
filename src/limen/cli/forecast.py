"""``limen forecast`` — predictive risk run at ``now + H`` hours.

Thin CLI over :func:`limen.agents.workflows.forecast.run_forecast`:
runs the shifted-window pipeline and renders a markdown report under
``./reports/``. Nothing is persisted — for scheduled predictive
*alerts* see the ``forecast_monitoring`` APScheduler job.

Env knobs:
    LIMEN_FORECAST_AOI          target AOI (default: every seeded AOI)
    LIMEN_FORECAST_HOURS        horizon, default 24 (Open-Meteo caps at 16 d)
    LIMEN_FORECAST_CELL_LIMIT   cap cells per AOI (smoke runs)
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from limen.agents.workflows.forecast import ForecastRun, run_forecast
from limen.core.logging import get_logger
from limen.data.db import lifespan_pool
from limen.data.repos.aoi_repo import list_aoi_ids
from limen.integrations._http import SharedHttpClient

log = get_logger(__name__)

REPORTS_DIR = Path("./reports")


def _write_report(run: ForecastRun) -> Path:
    top = sorted(run.cell_results, key=lambda c: c.score, reverse=True)[:10]
    top_ml = sorted(run.ml_by_cell.items(), key=lambda kv: kv[1], reverse=True)[:10]

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"forecast_{run.aoi_id}_{run.valuation_time:%Y-%m-%dT%H}h.md"
    lines = [
        f"# Limen forecast — AOI `{run.aoi_id}` a +{run.horizon_h}h",
        "",
        f"Valuation time: **{run.valuation_time.isoformat()}** "
        f"(generato {datetime.now(UTC).isoformat()})",
        "Pioggia: osservata + prevista Open-Meteo; antecedente 30 gg clampato a oggi.",
        f"Celle: **{len(run.cell_results)}**; distribuzione: {run.by_level}",
        "",
        "## Top 10 celle — champion deterministico",
        "",
        "| cella | score | classe |" + ("" if not run.ml_by_cell else " P(ML) |"),
        "|---|---|---|" + ("" if not run.ml_by_cell else "---|"),
    ]
    for c in top:
        ml = f" {run.ml_by_cell[c.cell_id]:.3f} |" if c.cell_id in run.ml_by_cell else ""
        cid = c.cell_id.replace("|", "\\|")
        lines.append(f"| {cid} | {c.score:.3f} | {c.level.value} |{ml}")
    if top_ml:
        lines += [
            "",
            "## Top 10 celle — challenger ML (probabilità calibrata)",
            "",
            "| cella | P(frana) |",
            "|---|---|",
            *(f"| {cid.replace('|', '\\|')} | {p:.3f} |" for cid, p in top_ml),
        ]
    else:
        lines += ["", "_Challenger ML non disponibile: solo champion._"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


async def run() -> int:
    horizon_h = int(os.getenv("LIMEN_FORECAST_HOURS", "24"))
    cell_limit_env = os.getenv("LIMEN_FORECAST_CELL_LIMIT")
    cell_limit = int(cell_limit_env) if cell_limit_env else None
    requested = os.getenv("LIMEN_FORECAST_AOI")

    try:
        async with lifespan_pool():
            aoi_ids = [requested] if requested else await list_aoi_ids()
            for aoi_id in aoi_ids:
                fc = await run_forecast(aoi_id=aoi_id, horizon_h=horizon_h, cell_limit=cell_limit)
                if not fc.cell_results:
                    log.warning("forecast.no_cells", aoi_id=aoi_id)
                    continue
                path = _write_report(fc)
                log.info(
                    "forecast.aoi.done",
                    aoi_id=aoi_id,
                    horizon_h=horizon_h,
                    cells=len(fc.cell_results),
                    by_level=fc.by_level,
                    ml_scored=len(fc.ml_by_cell),
                    report=str(path),
                )
    finally:
        await SharedHttpClient.aclose()
    return 0
