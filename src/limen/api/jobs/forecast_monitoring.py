"""Scheduled predictive sweep — the event-driven forecast pipeline.

Every ``FORECAST__INTERVAL_HOURS`` the job re-scores each AOI at
``now + FORECAST__HORIZON_HOURS`` using forecast rain. When the champion
predicts cells at/above ``FORECAST__MIN_LEVEL``, a *predictive* alert is
dispatched through the same notification channels as operational alerts
(webhook → OpenClaw, Telegram, …) — clearly labelled as a forecast and
deduplicated per (AOI, horizon) in ``forecast_dispatches``, a ledger kept
separate from the operational per-cell dedup so the two paths can never
mask each other. Deterministic summary only: no LLM in the alert path.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from limen.agents.workflows.forecast import ForecastRun, run_forecast
from limen.api.dependencies import AppDependencies
from limen.core.logging import get_logger
from limen.core.models.context import AggregateAssessment, CellRiskRecord
from limen.core.models.risk import RiskLevel
from limen.data.repos.aoi_repo import list_aoi_ids
from limen.data.repos.forecast_dispatches_repo import dispatched_within, record_dispatch
from limen.notifications.base import AlertPayload, build_alert_payload, level_at_least

log = get_logger(__name__)

_LEVEL_FROM_STRING = {lvl.value: lvl for lvl in RiskLevel}


def _forecast_summary_it(run: ForecastRun, triggered: list[CellRiskRecord]) -> str:
    """Deterministic Italian summary — only numbers from the forecast run."""
    counts = ", ".join(f"{lvl}: {n}" for lvl, n in sorted(run.by_level.items()))
    top = triggered[0]
    return (
        f"PREVISIONE Limen a +{run.horizon_h} ore "
        f"(valida al {run.valuation_time:%d/%m %H:%M} UTC) per AOI {run.aoi_id}: "
        f"{len(triggered)} celle previste a livello {top.level.value} o superiore "
        f"(distribuzione {counts}). Cella di picco {top.cell_id} con punteggio "
        f"previsto {top.score:.2f}. Stima basata su pioggia prevista Open-Meteo; "
        f"il quadro operativo resta quello del monitoraggio orario."
    )


def build_forecast_payload(run: ForecastRun, triggered: list[CellRiskRecord]) -> AlertPayload:
    """Assemble the predictive AlertPayload (deterministic, forecast-labelled)."""
    from limen.config.settings import get_settings

    pipeline_version = f"v1-forecast+{run.horizon_h}h"
    assessment = AggregateAssessment(
        aoi_id=run.aoi_id,
        horizon=f"{run.horizon_h}h",
        model_version=pipeline_version,
        pipeline_version=pipeline_version,
        valuation_time=run.valuation_time,
        n_cells=len(run.cell_results),
        cells_high_or_above=sum(
            1 for c in run.cell_results if level_at_least(c.level, RiskLevel.High)
        ),
        cells_by_level=run.by_level,
        top_cells=triggered[:5],
    )
    payload = build_alert_payload(
        assessment=assessment,
        prioritised=[(c, c.score) for c in triggered],
        settings=get_settings().alert,
        dispatched_at=datetime.now(UTC),
    )
    return payload.model_copy(
        update={
            "summary_it": _forecast_summary_it(run, triggered),
            "pipeline_version": pipeline_version,
        }
    )


async def run_forecast_monitoring(deps: AppDependencies) -> dict[str, int]:
    """Predictive sweep over every AOI; returns cells-triggered per AOI."""
    cfg = deps.settings.forecast
    min_level = _LEVEL_FROM_STRING.get(cfg.min_level, RiskLevel.High)
    out: dict[str, int] = {}

    for aoi_id in await list_aoi_ids():
        try:
            fc = await run_forecast(
                aoi_id=aoi_id,
                horizon_h=cfg.horizon_hours,
                cell_limit=cfg.cell_limit,
                settings=deps.settings,
            )
            triggered = sorted(
                (c for c in fc.cell_results if level_at_least(c.level, min_level)),
                key=lambda c: c.score,
                reverse=True,
            )
            out[aoi_id] = len(triggered)
            if not triggered:
                continue
            if await dispatched_within(
                aoi_id,
                horizon_h=cfg.horizon_hours,
                window=timedelta(hours=cfg.dedup_window_hours),
            ):
                log.info("job.forecast.deduped", aoi_id=aoi_id, horizon_h=cfg.horizon_hours)
                continue

            payload = build_forecast_payload(fc, triggered)
            outcomes = await deps.notification_dispatcher.dispatch(payload)
            await record_dispatch(
                aoi_id=aoi_id,
                horizon_h=cfg.horizon_hours,
                max_level=triggered[0].level.value,
                max_score=triggered[0].score,
                cells_alerted=len(triggered),
                channels=outcomes,
                summary=payload.summary_it,
            )
            log.info(
                "job.forecast.dispatched",
                aoi_id=aoi_id,
                horizon_h=cfg.horizon_hours,
                cells=len(triggered),
                channels=outcomes,
            )
        except Exception as exc:  # never bring the scheduler down
            log.error(
                "job.forecast.error",
                aoi_id=aoi_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )
    log.info("job.forecast.done", per_aoi=out)
    return out
