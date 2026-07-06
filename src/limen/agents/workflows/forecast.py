"""Predictive (``now + H``) run of the scoring pipeline.

Shared by ``limen forecast`` (on-demand report) and the scheduled
forecast-monitoring job (event-driven predictive alerts). The trimmed
workflow stops at RiskScoring: no escalation, no LLM, no persistence —
callers decide what to do with the results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from limen.agents.executors import (
    AreaResolverExecutor,
    FireCheckExecutor,
    MeteoFetchExecutor,
    RiskScoringExecutor,
    SeismicCheckExecutor,
    StaticFactorsExecutor,
)
from limen.agents.workflow_runtime.builder import WorkflowBuilder
from limen.config.settings import Settings, get_settings
from limen.core.features.assembler import assemble_bundles
from limen.core.logging import get_logger
from limen.core.models.context import CellRiskRecord, MonitoringContext
from limen.core.scoring.resolver import resolve_challenger, resolve_scoring_engine
from limen.data.caching.cached_openmeteo import CachedOpenMeteoClient

log = get_logger(__name__)


class ClampedApiClient(CachedOpenMeteoClient):
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


@dataclass(frozen=True, slots=True)
class ForecastRun:
    """Outcome of one predictive run over an AOI."""

    aoi_id: str
    horizon_h: int
    valuation_time: datetime
    cell_results: list[CellRiskRecord] = field(default_factory=list)
    ml_by_cell: dict[str, float] = field(default_factory=dict)

    @property
    def by_level(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for c in self.cell_results:
            out[c.level.value] = out.get(c.level.value, 0) + 1
        return out


async def run_forecast(
    *,
    aoi_id: str,
    horizon_h: int,
    cell_limit: int | None = None,
    settings: Settings | None = None,
) -> ForecastRun:
    """Score ``aoi_id`` at ``now + horizon_h`` with champion + ML challenger."""
    settings = settings or get_settings()
    champion = resolve_scoring_engine(settings=settings)
    challenger = resolve_challenger(settings=settings)

    wf = (
        WorkflowBuilder("limen-landslide-forecast")
        .add(AreaResolverExecutor(cell_limit=cell_limit))
        .add(StaticFactorsExecutor())
        .add(
            MeteoFetchExecutor(
                client=ClampedApiClient(),
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

    ml_by_cell: dict[str, float] = {}
    if challenger is not None and out.cell_results:
        for bundle in assemble_bundles(out):
            ml_by_cell[bundle.cell_id] = challenger.score(bundle).score

    return ForecastRun(
        aoi_id=aoi_id,
        horizon_h=horizon_h,
        valuation_time=valuation_time,
        cell_results=list(out.cell_results),
        ml_by_cell=ml_by_cell,
    )


__all__ = ["ClampedApiClient", "ForecastRun", "run_forecast"]
