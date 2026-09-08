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
from limen.config.settings import AlertSettings, RateLimitSettings, Settings, get_settings
from limen.core.logging import get_logger
from limen.core.models.context import CellRiskRecord, MonitoringContext
from limen.core.models.hazard import DEFAULT_HAZARD, HazardType
from limen.core.models.risk import RiskLevel
from limen.core.scoring.exposure import exposure_factor_from_row
from limen.core.scoring.regional_thresholds import load_hazard_thresholds
from limen.data.db import acquire
from limen.data.repos.alert_aggregates_repo import (
    comuni_alerted_within,
    comuni_queued,
    insert_aggregates,
    record_sends,
    sends_last_hour,
)
from limen.data.repos.alert_dispatches_repo import (
    AlertDispatchRow,
    cells_dispatched_within,
)
from limen.data.repos.alert_dispatches_repo import (
    insert_many as insert_dispatches,
)
from limen.notifications.base import (
    AlertPayload,
    ComuneSummary,
    build_alert_payload,
    level_at_least,
)
from limen.notifications.governance import (
    ComuneAggregate,
    aggregate_by_comune,
    rate_limit_verdict,
    summarise_comuni_it,
    worst_level,
)
from limen.observability.metrics import get_metrics

if TYPE_CHECKING:
    from limen.notifications.dispatcher import NotificationDispatcher

log = get_logger(__name__)


_LEVEL_FROM_STRING = {lvl.value: lvl for lvl in RiskLevel}


def _resolve_threshold(min_level: str) -> RiskLevel:
    return _LEVEL_FROM_STRING.get(min_level, RiskLevel.High)


async def _load_exposure_factors(
    cell_ids: list[str], hazard: HazardType = DEFAULT_HAZARD
) -> dict[str, float]:
    """Exposure multiplier for the candidate cells only.

    Same shared formula as ``/api/alerts`` (``limen.core.scoring.exposure``):
    CORINE urban flags + distance from the OSM road/rail network, with the
    CORINE 12x flags as fallback. Cells without a factors row get 0
    (priority == score).

    Weights come from **the hazard's own** YAML: what makes a cell exposed to
    a flood is not what makes it exposed to a slope failure, and using the
    landslide block for another hazard would order its alerts by the wrong
    priority.
    """
    cfg = load_hazard_thresholds(hazard).exposure
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT c.cell_id,
                   (c.landuse_code LIKE '11%') AS urban_here,
                   (c.landuse_code LIKE '12%') AS infra_here,
                   c.near_urban AS urban_near,
                   c.near_infra AS infra_near,
                   c.distance_to_road_m, c.distance_to_rail_m,
                   c.nearest_road_class,
                   c.wui_proximity_norm
            FROM cell_static_factors c
            WHERE c.cell_id = ANY($1::text[])
            """,
            cell_ids,
        )
    return {str(r["cell_id"]): exposure_factor_from_row(r, cfg)[0] for r in rows}


async def _comuni_for_cells(cell_ids: list[str]) -> dict[str, str]:
    """Comune name per cell (from the precomputed cell_comune tag)."""
    if not cell_ids:
        return {}
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT cc.cell_id, c.name
            FROM cell_comune cc JOIN comuni c ON c.istat_code = cc.istat_code
            WHERE cc.cell_id = ANY($1::text[])
            """,
            cell_ids,
        )
    return {str(r["cell_id"]): str(r["name"]) for r in rows}


async def _comune_tags(cell_ids: list[str]) -> tuple[dict[str, str], dict[str, str]]:
    """``(cella → codice ISTAT, codice ISTAT → nome)`` per le celle date.

    Due mappe e non una: la dedup e il rollup si fanno sul **codice**, che è
    stabile, mentre il nome serve solo alla frase italiana. Due comuni possono
    chiamarsi allo stesso modo in regioni diverse, e raggrupparli per nome
    unirebbe territori che non si toccano.
    """
    if not cell_ids:
        return {}, {}
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT cc.cell_id, cc.istat_code, c.name
            FROM cell_comune cc JOIN comuni c ON c.istat_code = cc.istat_code
            WHERE cc.cell_id = ANY($1::text[])
            """,
            cell_ids,
        )
    per_cella = {str(r["cell_id"]): str(r["istat_code"]) for r in rows}
    nomi = {str(r["istat_code"]): str(r["name"]) for r in rows}
    return per_cella, nomi


def _to_summaries(aggregates: list[ComuneAggregate]) -> list[ComuneSummary]:
    return [
        ComuneSummary(
            istat_code=a.istat_code,
            comune=a.comune,
            hazard_type=a.hazard,
            max_level=a.max_level,
            max_score=a.max_score,
            cells_count=a.cells_count,
            top_cell_ids=[cid for cid, _, _ in a.top_cells],
        )
        for a in aggregates
    ]


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
        rate_limit: RateLimitSettings | None = None,
        hazard: HazardType = DEFAULT_HAZARD,
    ) -> None:
        super().__init__(name="AlertDispatch")
        self._dispatcher = dispatcher
        self._alert_settings = alert_settings
        # Il governo del volume (#59) è iniettabile come le soglie: un test
        # che verifica il digest deve poter fissare il limite senza toccare
        # l'ambiente.
        self._rate_limit = rate_limit
        # Dedup is per hazard: a landslide alert must not suppress a flood
        # alert on the same cell inside the window.
        self._hazard = hazard

    def _settings(self, ctx_settings: Settings | None = None) -> AlertSettings:
        if self._alert_settings is not None:
            return self._alert_settings
        return (ctx_settings or get_settings()).alert

    def _governance(self, ctx_settings: Settings | None = None) -> RateLimitSettings:
        if self._rate_limit is not None:
            return self._rate_limit
        return (ctx_settings or get_settings()).notifications.rate_limit

    @handler
    async def run(self, ctx: MonitoringContext) -> MonitoringContext:
        if ctx.assessment is None:
            log.warning("alert_dispatch.skip", reason="no assessment in ctx")
            return ctx

        alert_settings = self._settings(None)
        threshold = _resolve_threshold(alert_settings.min_level)

        # V1.5 — hard-escalation cells (acceleration ≥ alarm OR inverse-velocity
        # ≤ alarm) bypass the level threshold entirely. The kinematic regime
        # is a precursor signal the operator should see regardless of the
        # current aggregate level.
        seen: set[str] = set()
        above_threshold: list[CellRiskRecord] = []
        for r in ctx.cell_results:
            if r.cell_id in seen:
                continue
            # Below-High levels alert only on genuinely predisposed cells:
            # "moderate rain on a susceptible slope", not "moderate rain
            # anywhere". Which component carries the predisposition is the
            # hazard's business — S for a slope, fuel for a wildfire — so the
            # gate asks the breakdown instead of naming one. High+ and hard
            # escalation bypass it.
            selective = (
                level_at_least(r.level, RiskLevel.High)
                or r.predisposition >= alert_settings.min_static_s
            )
            if r.hard_escalation or (level_at_least(r.level, threshold) and selective):
                above_threshold.append(r)
                seen.add(r.cell_id)
        if not above_threshold:
            log.info(
                "alert_dispatch.below_threshold",
                aoi_id=ctx.aoi_id,
                threshold=threshold.value,
                cells_scored=len(ctx.cell_results),
            )
            return ctx

        # Priority — exposure-weighted score.
        exposure = await _load_exposure_factors([r.cell_id for r in above_threshold], self._hazard)
        prioritised: list[tuple[CellRiskRecord, float]] = []
        for record in above_threshold:
            mult = 1.0 + exposure.get(record.cell_id, 0.0)
            prioritised.append((record, record.score * mult))
        prioritised.sort(key=lambda pr: pr[1], reverse=True)

        # Dedup — skip cells alerted inside the window.
        window = timedelta(minutes=alert_settings.dedup_window_minutes)
        candidate_ids = [r.cell_id for r, _ in prioritised]
        suppressed = await cells_dispatched_within(
            candidate_ids, window=window, hazard=self._hazard
        )
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

        # --- governo degli alert (#59) -----------------------------------
        # Il rollup per comune viene *prima* del dispatch, perché è ciò che
        # decide quanti messaggi escono. Migliaia di celle sopra soglia in un
        # fronte esteso sono decine di comuni, non migliaia di avvisi.
        now = datetime.now(UTC)
        istat_per_cella, nomi_comuni = await _comune_tags([r.cell_id for r, _ in deduped])

        # Dedup comunale: due celle vicine dello stesso paese sono lo stesso
        # avviso ricevuto due volte. Resta per pericolo.
        gov = self._governance()
        comune_window = timedelta(minutes=alert_settings.dedup_window_minutes)
        comuni_soppressi = await comuni_alerted_within(
            set(istat_per_cella.values()), window=comune_window, hazard=self._hazard
        )
        rimasti = [
            (r, p) for r, p in deduped if istat_per_cella.get(r.cell_id) not in comuni_soppressi
        ]
        if not rimasti:
            log.info(
                "alert_dispatch.comune_dedup_all",
                aoi_id=ctx.aoi_id,
                comuni_suppressed=len(comuni_soppressi),
                window_minutes=alert_settings.dedup_window_minutes,
            )
            return ctx.with_update(
                dispatched_alerts=[
                    f"dedup-suppressed comune={c} hazard={self._hazard.value}"
                    for c in sorted(comuni_soppressi)
                ]
            )

        aggregates = aggregate_by_comune(
            rimasti,
            comuni=nomi_comuni,
            istat_codes=istat_per_cella,
            aoi_id=ctx.aoi_id,
            hazard=self._hazard,
        )
        livello_max = worst_level(aggregates)

        # Rate limit: il conteggio è per canale, quindi il verdetto lo decide
        # il canale **più carico**. Spedire a metà dei canali e accodare per
        # l'altra metà darebbe due messaggi diversi sullo stesso evento.
        canali = self._dispatcher.channel_names if self._dispatcher is not None else []
        carico = max([await sends_last_hour(c, now=now) for c in canali], default=0)
        verdict = rate_limit_verdict(
            sends_last_hour=carico,
            max_per_hour=gov.max_per_hour,
            level=livello_max,
            bypass_level=_resolve_threshold(gov.bypass_level),
            enabled=gov.enabled,
        )

        if verdict == "queue":
            # Già in coda dal ciclo precedente: il riepilogo li nominerebbe
            # due volte con lo stesso numero. La dedup per cella non li ha
            # fermati perché un ciclo trattenuto non scrive in
            # `alert_dispatches` — non è uscito niente.
            gia_in_coda = await comuni_queued(
                {a.istat_code for a in aggregates if a.istat_code}, hazard=self._hazard
            )
            nuovi = [a for a in aggregates if a.istat_code not in gia_in_coda]
            await insert_aggregates(nuovi, state="queued")
            log.info(
                "alert_dispatch.queued",
                aoi_id=ctx.aoi_id,
                hazard=self._hazard.value,
                comuni=len(nuovi),
                comuni_already_queued=len(aggregates) - len(nuovi),
                cells=len(rimasti),
                level=livello_max.value,
                sends_last_hour=carico,
                max_per_hour=gov.max_per_hour,
            )
            # Nessuna riga in `alert_dispatches`: non è uscito niente, e
            # registrarlo come spedito farebbe sopprimere dalla dedup un
            # avviso che nessuno ha ricevuto.
            return ctx.with_update(
                dispatched_alerts=[
                    f"digest-queued comune={a.label} hazard={a.hazard.value} "
                    f"cells={a.cells_count} level={a.max_level.value}"
                    for a in nuovi
                ]
            )

        deduped = rimasti
        comuni = await _comuni_for_cells([r.cell_id for r, _ in deduped[: alert_settings.top_k]])
        payload: AlertPayload = build_alert_payload(
            assessment=ctx.assessment,
            prioritised=deduped,
            settings=alert_settings,
            dispatched_at=now,
            comuni=comuni,
            aggregates=_to_summaries(aggregates),
            summary_override=summarise_comuni_it(aggregates),
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
        await insert_aggregates(aggregates, state="sent", channels=outcomes)
        await record_sends(outcomes, kind="alert", aggregates=len(aggregates))

        # Persist + emit metric.
        rows = [
            AlertDispatchRow(
                hazard_type=self._hazard,
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
