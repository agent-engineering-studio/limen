"""``limen forecast`` — predictive risk run at ``now + H`` hours.

Runs the scoring pipeline with ``valuation_time`` shifted forward so the
Open-Meteo *forecast* window blends observed past with predicted future
rain. Champion (and ML challenger, when resolvable) score the same
bundles. Nothing is persisted: no risk_assessments, no model_runs, no
alerts — the output is a report under ``./reports/``.

Env knobs:
    LIMEN_FORECAST_AOI          target AOI (default: every seeded AOI)
    LIMEN_FORECAST_HOURS        horizon, default 24 (Open-Meteo caps at 16 d)
    LIMEN_FORECAST_CELL_LIMIT   cap cells per AOI (smoke runs)
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from limen.agents.executors import (
    AreaResolverExecutor,
    FireCheckExecutor,
    MeteoFetchExecutor,
    RiskScoringExecutor,
    SeismicCheckExecutor,
    StaticFactorsExecutor,
)
from limen.agents.workflow_runtime.builder import WorkflowBuilder
from limen.config.settings import get_settings
from limen.core.features.assembler import assemble_bundles
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext
from limen.core.scoring.resolver import resolve_challenger, resolve_scoring_engine
from limen.data.caching.cached_openmeteo import CachedOpenMeteoClient
from limen.data.db import lifespan_pool
from limen.data.repos.aoi_repo import list_aoi_ids
from limen.integrations._http import SharedHttpClient

log = get_logger(__name__)

REPORTS_DIR = Path("./reports")


class _ClampedApiClient(CachedOpenMeteoClient):
    """ERA5 archive lags ~5 days; a future ``as_of`` would silently drop the
    most recent — and most predictive — antecedent days. Clamp to today: the
    forecast rain itself is already in the hourly window."""

    async def get_api(
        self,
        *,
        aoi_id: str,
        bbox: tuple[float, float, float, float],
        as_of: date,
        days: int,
    ) -> dict[str, float]:
        today = datetime.now(UTC).date()
        return await super().get_api(aoi_id=aoi_id, bbox=bbox, as_of=min(as_of, today), days=days)


async def _forecast_aoi(*, aoi_id: str, horizon_h: int, cell_limit: int | None) -> Path | None:
    settings = get_settings()
    champion = resolve_scoring_engine(settings=settings)
    challenger = resolve_challenger(settings=settings)

    wf = (
        WorkflowBuilder("limen-landslide-forecast")
        .add(AreaResolverExecutor(cell_limit=cell_limit))
        .add(StaticFactorsExecutor())
        .add(
            MeteoFetchExecutor(
                client=_ClampedApiClient(),
                rain_node_deg=settings.meteo_rain_node_deg,
            )
        )
        .add(SeismicCheckExecutor())
        .add(FireCheckExecutor())
        .add(RiskScoringExecutor(engine=champion))
        .build()
    )

    valuation_time = datetime.now(UTC) + timedelta(hours=horizon_h)
    ctx = MonitoringContext(aoi_id=aoi_id, valuation_time=valuation_time)
    result = await wf.run(ctx)
    out = result.context
    if not out.cell_results:
        log.warning("forecast.no_cells", aoi_id=aoi_id)
        return None

    ml_by_cell: dict[str, float] = {}
    if challenger is not None:
        for bundle in assemble_bundles(out):
            ml_by_cell[bundle.cell_id] = challenger.score(bundle).score

    by_level: dict[str, int] = {}
    for c in out.cell_results:
        by_level[c.level.value] = by_level.get(c.level.value, 0) + 1
    top = sorted(out.cell_results, key=lambda c: c.score, reverse=True)[:10]
    top_ml = sorted(ml_by_cell.items(), key=lambda kv: kv[1], reverse=True)[:10]

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"forecast_{aoi_id}_{valuation_time:%Y-%m-%dT%H}h.md"
    lines = [
        f"# Limen forecast — AOI `{aoi_id}` a +{horizon_h}h",
        "",
        f"Valuation time: **{valuation_time.isoformat()}** "
        f"(generato {datetime.now(UTC).isoformat()})",
        "Pioggia: osservata + prevista Open-Meteo; antecedente 30 gg clampato a oggi.",
        f"Celle: **{len(out.cell_results)}**; distribuzione: {by_level}",
        "",
        "## Top 10 celle — champion deterministico",
        "",
        "| cella | score | classe |" + ("" if not ml_by_cell else " P(ML) |"),
        "|---|---|---|" + ("" if not ml_by_cell else "---|"),
    ]
    for c in top:
        ml = f" {ml_by_cell[c.cell_id]:.3f} |" if c.cell_id in ml_by_cell else ""
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

    log.info(
        "forecast.aoi.done",
        aoi_id=aoi_id,
        horizon_h=horizon_h,
        cells=len(out.cell_results),
        by_level=by_level,
        ml_scored=len(ml_by_cell),
        report=str(path),
    )
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
                await _forecast_aoi(aoi_id=aoi_id, horizon_h=horizon_h, cell_limit=cell_limit)
    finally:
        await SharedHttpClient.aclose()
    return 0
