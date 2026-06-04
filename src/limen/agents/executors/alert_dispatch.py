"""Alert-dispatch executor — Phase 7 (real multi-channel).

Pipeline:

1. Filter ``ctx.cell_results`` to cells whose level ≥ ``AlertSettings.min_level``.
2. Look up per-cell exposure from ``cell_static_factors``; compute
   ``priority = score * (1 + exposure_factor)``. When exposure is
   unknown, priority falls back to the raw score.
3. Drop cells already dispatched within the dedup window
   (``alert_dispatches.dispatched_at`` query).
4. Sort by priority (desc), build a single :class:`AlertPayload`,
   dispatch to every channel via
   :class:`NotificationDispatcher`.
5. Persist one row per cell in ``alert_dispatches`` with the
   per-channel outcomes, emit the ``landslide.alert.dispatched``
   counter (one increment per cell * channel succeeded).
6. Stash human-readable strings on ``ctx.dispatched_alerts`` so the
   monitor endpoint can surface them.

Graceful degradation: if the dispatcher is missing (V1 stub mode) or
every enabled channel is unconfigured, we still execute the dedup
record-keeping step so the next workflow run won't re-fire. With no
channels configured at all, this is exactly the V1 logging behaviour.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from limen.agents.workflow_runtime.executor import Executor, handler
from limen.config.settings import AlertSettings, Settings, get_settings
from limen.core.logging import get_logger
from limen.core.models.context import CellRiskRecord, MonitoringContext
from limen.core.models.risk import RiskLevel
from limen.data.db import acquire
from limen.data.repos.alert_dispatches_repo import (
    AlertDispatchRow,
    cells_dispatched_within,
)
from limen.data.repos.alert_dispatches_repo import (
    insert_many as insert_dispatches,
)
from limen.notifications.base import (
    AlertPayload,
    build_alert_payload,
    level_at_least,
)
from limen.observability.metrics import get_metrics

if TYPE_CHECKING:
    from limen.notifications.dispatcher import NotificationDispatcher

log = get_logger(__name__)


_LEVEL_FROM_STRING = {lvl.value: lvl for lvl in RiskLevel}


def _resolve_threshold(min_level: str) -> RiskLevel:
    return _LEVEL_FROM_STRING.get(min_level, RiskLevel.High)


def _exposure_factor(
    *,
    population: int | None,
    buildings: int | None,
    infra_density: float | None,
) -> float:
    """Bounded exposure multiplier in roughly ``[0, 2]``.

    The weighting is empirical (no V1 calibration data yet). Designed so
    that a cell with no exposure data gets a multiplier of 0 (priority
    == score), while a heavily-exposed cell can roughly double its
    priority. V1.5 calibration on real population/buildings density
    will replace these magic numbers with a YAML knob.
    """
    components: list[float] = []
    if population is not None and population > 0:
        components.append(min(1.0, population / 1000.0))
    if buildings is not None and buildings > 0:
        components.append(min(1.0, buildings / 100.0))
    if infra_density is not None and infra_density > 0:
        components.append(min(1.0, float(infra_density)))
    return sum(components) / max(1, len(components)) if components else 0.0


async def _load_exposure(
    aoi_id: str,
) -> dict[str, tuple[int | None, int | None, float | None]]:
    """Load per-cell exposure for one AOI.

    Returns a mapping ``cell_id → (population, buildings, infra_density)``.
    Missing rows yield ``(None, None, None)`` so the priority function
    can fall back cleanly.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT c.cell_id, c.population_count, c.buildings_count,
                   c.infra_density_norm
            FROM cell_static_factors c
            JOIN grid_cells g ON g.id = c.cell_id
            WHERE g.aoi_id = $1
            """,
            aoi_id,
        )
    return {
        str(r["cell_id"]): (
            int(r["population_count"]) if r["population_count"] is not None else None,
            int(r["buildings_count"]) if r["buildings_count"] is not None else None,
            float(r["infra_density_norm"]) if r["infra_density_norm"] is not None else None,
        )
        for r in rows
    }


class AlertDispatchExecutor(Executor):
    """V1 alert dispatcher.

    The executor accepts:

    * ``dispatcher`` — the :class:`NotificationDispatcher`. ``None``
      keeps Phase 4's logging-stub behaviour for environments without
      any channels configured (this is what tests rely on).
    * ``alert_settings`` — overrides ``Settings.alert`` (useful for
      tests that need a deterministic ``now`` or a custom threshold).
    """

    def __init__(
        self,
        dispatcher: NotificationDispatcher | None = None,
        *,
        alert_settings: AlertSettings | None = None,
    ) -> None:
        super().__init__(name="AlertDispatch")
        self._dispatcher = dispatcher
        self._alert_settings = alert_settings

    def _settings(self, ctx_settings: Settings | None = None) -> AlertSettings:
        if self._alert_settings is not None:
            return self._alert_settings
        return (ctx_settings or get_settings()).alert

    @handler
    async def run(self, ctx: MonitoringContext) -> MonitoringContext:
        if ctx.assessment is None:
            log.warning("alert_dispatch.skip", reason="no assessment in ctx")
            return ctx

        alert_settings = self._settings(None)
        threshold = _resolve_threshold(alert_settings.min_level)

        above_threshold: list[CellRiskRecord] = [
            r for r in ctx.cell_results if level_at_least(r.level, threshold)
        ]
        if not above_threshold:
            log.info(
                "alert_dispatch.below_threshold",
                aoi_id=ctx.aoi_id,
                threshold=threshold.value,
                cells_scored=len(ctx.cell_results),
            )
            return ctx

        # Priority — exposure-weighted score.
        exposure = await _load_exposure(ctx.aoi_id)
        prioritised: list[tuple[CellRiskRecord, float]] = []
        for record in above_threshold:
            pop, bld, infra = exposure.get(record.cell_id, (None, None, None))
            mult = 1.0 + _exposure_factor(population=pop, buildings=bld, infra_density=infra)
            prioritised.append((record, record.score * mult))
        prioritised.sort(key=lambda pr: pr[1], reverse=True)

        # Dedup — skip cells alerted inside the window.
        window = timedelta(minutes=alert_settings.dedup_window_minutes)
        candidate_ids = [r.cell_id for r, _ in prioritised]
        suppressed = await cells_dispatched_within(candidate_ids, window=window)
        deduped = [(r, p) for r, p in prioritised if r.cell_id not in suppressed]
        if not deduped:
            log.info(
                "alert_dispatch.dedup_all",
                aoi_id=ctx.aoi_id,
                window_minutes=alert_settings.dedup_window_minutes,
                suppressed=len(suppressed),
            )
            return ctx.with_update(
                dispatched_alerts=[
                    f"dedup-suppressed cell={c} window={alert_settings.dedup_window_minutes}m"
                    for c in suppressed
                ]
            )

        # Build the payload + dispatch.
        now = datetime.now(UTC)
        payload: AlertPayload = build_alert_payload(
            assessment=ctx.assessment,
            prioritised=deduped,
            settings=alert_settings,
            dispatched_at=now,
        )
        outcomes: dict[str, bool] = {}
        if self._dispatcher is not None:
            outcomes = await self._dispatcher.dispatch(payload)
        else:
            log.info(
                "alert_dispatch.stub",
                aoi_id=ctx.aoi_id,
                cells=len(deduped),
                note="no notification dispatcher configured; logging only",
            )

        # Persist + emit metric.
        rows = [
            AlertDispatchRow(
                cell_id=record.cell_id,
                aoi_id=ctx.aoi_id,
                level=record.level.value,
                score=record.score,
                priority=priority,
                channels=outcomes,
                summary=payload.summary_it,
            )
            for record, priority in deduped
        ]
        await insert_dispatches(rows)

        metrics = get_metrics()
        successful_channels = [name for name, ok in outcomes.items() if ok]
        for record, _ in deduped:
            attrs = {
                "aoi_id": ctx.aoi_id,
                "level": record.level.value,
                "channels_succeeded": ",".join(successful_channels) or "none",
            }
            # One alert per cell * per successful channel (intentional:
            # otherwise a single channel failure would understate volume).
            for _ch in successful_channels:
                metrics.alert_dispatched.add(1, attrs)
            if not successful_channels:
                metrics.alert_dispatched.add(0, attrs)

        dispatched_lines = [
            f"aoi={ctx.aoi_id} cell={r.cell_id} level={r.level.value} "
            f"score={r.score:.3f} priority={p:.3f} channels={outcomes}"
            for r, p in deduped
        ]
        log.info(
            "alert_dispatch.done",
            aoi_id=ctx.aoi_id,
            cells_dispatched=len(deduped),
            cells_suppressed=len(suppressed),
            outcomes=outcomes,
        )
        return ctx.with_update(dispatched_alerts=dispatched_lines)


__all__ = ["AlertDispatchExecutor"]
