"""Advance the FWI chain for the AOI's weather nodes (#62).

The step between "what the weather is" and "what that means for fire". It
reads the meteo the shared MeteoFetch already pulled, takes each node's noon
observation, advances the recursive codes from the state on disk, writes the
new day, and puts the result on the context so the assembler can hand each
cell the chain of its nearest node.

It runs **before** scoring and only in the wildfire workflow: the chain has
no meaning for a slope, and stepping it in the landslide sweep would burn a
write per node per tick for nothing.

It also serves the forecast sweep, which asks for a day in the future. Same
walk, one difference: **future days are computed but never written**. A
forecast row in ``fwi_state`` would become tomorrow's predecessor and the
operational chain would end up recursing on a prediction.

Degrades, never raises. A node with no usable observation keeps yesterday's
row and the cells around it score with a stale-but-real chain; a node with no
chain at all yields no fire weather, and the engine reports the cell dark and
flagged rather than inventing an index.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from limen.agents.workflow_runtime.executor import Executor, handler
from limen.core.logging import get_logger
from limen.core.models.context import MonitoringContext
from limen.core.models.hazard import HazardType
from limen.core.models.risk import FireWeatherState
from limen.core.scoring.regional_thresholds import (
    WildfireThresholds,
    load_hazard_thresholds,
)
from limen.data.repos import fwi_state_repo
from limen.data.repos.fwi_state_repo import NodeDay, StoredChain
from limen.integrations.openmeteo.client import OpenMeteoHttpClient
from limen.integrations.openmeteo.dtos import FireWeatherObservation, MeteoSnapshot
from limen.integrations.openmeteo.grid import build_snapped_nodes

log = get_logger(__name__)


class FwiUpdateExecutor(Executor):
    """Step the Van Wagner chain one day and publish it on the context."""

    def __init__(
        self,
        *,
        thresholds: WildfireThresholds | None = None,
        client: OpenMeteoHttpClient | None = None,
    ) -> None:
        super().__init__(name="FwiUpdate")
        self._client = client or OpenMeteoHttpClient()
        loaded = thresholds or load_hazard_thresholds(HazardType.WILDFIRE)
        if not isinstance(loaded, WildfireThresholds):
            raise TypeError(f"FwiUpdate needs WildfireThresholds, got {type(loaded).__name__}")
        self._t = loaded

    @handler
    async def run(self, ctx: MonitoringContext) -> MonitoringContext:
        # Late import: the backfill module owns the walk, and importing it at
        # module scope would pull the CLI's dependencies into every workflow.
        from limen.cli.fwi_backfill import advance_node, params_from

        if ctx.bbox is None:
            log.warning("fwi_update.skip", aoi_id=ctx.aoi_id, reason="no bbox")
            return ctx

        spacing = self._t.fwi.node_spacing_deg
        nodes = build_snapped_nodes(ctx.bbox, spacing=spacing)
        target = ctx.valuation_time.date()
        today = datetime.now(UTC).date()

        # The chain advances by day, the sweep runs by hour. Re-walking a day
        # already on disk costs a full grid fetch -- four variables per node
        # per day -- to land on the same numbers, and Open-Meteo bills by
        # location-variable-day: 1446 nodes taken 24 times a day is what
        # exhausted the free daily quota and left every cell with no chain at
        # all (#142). Once the day is written, read it. The forecast that
        # firms up during the day is precision nobody reads off a danger
        # index EFFIS publishes once a day.
        if nodes:
            already = await fwi_state_repo.read_day(nodes, target)
            if all(state is not None for state in already):
                log.info(
                    "fwi_update.stored",
                    aoi_id=ctx.aoi_id,
                    nodes=len(nodes),
                    day=target.isoformat(),
                )
                return ctx.with_update(fwi_nodes=tuple(nodes), fwi_by_node=tuple(already))

        stored_by_node = [
            await fwi_state_repo.latest_before(lon, lat, target) for lon, lat in nodes
        ]
        params = params_from(self._t)
        rows: list[NodeDay] = []
        chains: list[FireWeatherState | None] = []
        # One fetch for the whole grid, covering only the days some node still
        # has to walk plus the one before it (the 24 h rain of the first
        # noon). Asking for `max_gap_days` unconditionally multiplied every
        # request by seven to re-read days already on disk.
        observations = await self._observations(nodes, self._span(target, stored_by_node))
        for (lon, lat), by_day, stored in zip(nodes, observations, stored_by_node, strict=True):
            # Walk from the day after the stored state, so a sweep two days
            # into the future does not skip the drying in between. Bounded by
            # the same gap the backfill uses: beyond it the state is a fiction
            # and `advance_node` restarts from the seed anyway.
            first = target
            if stored is not None:
                first = max(
                    stored.day + timedelta(days=1),
                    target - timedelta(days=self._t.fwi.max_gap_days),
                )
            days = [first + timedelta(days=i) for i in range((target - first).days + 1)]
            if not days:
                chains.append(None)
                continue
            walked = await advance_node(
                lon=lon,
                lat=lat,
                observations=by_day,
                days=days,
                params=params,
                max_gap_days=self._t.fwi.max_gap_days,
            )
            # Only the past is written. A forecast row would become tomorrow's
            # predecessor and the operational chain would recurse on it.
            rows.extend(r for r in walked if r.day <= today)
            final = next((r for r in reversed(walked) if r.day == target), None)
            chains.append(
                None
                if final is None
                else FireWeatherState(
                    day=final.day,
                    ffmc=final.outputs.state.ffmc,
                    dmc=final.outputs.state.dmc,
                    dc=final.outputs.state.dc,
                    isi=final.outputs.isi,
                    bui=final.outputs.bui,
                    fwi=final.outputs.fwi,
                    chain_days=final.chain_days,
                )
            )
        if rows:
            await fwi_state_repo.upsert_many(rows)

        covered = sum(1 for c in chains if c is not None)
        log.info(
            "fwi_update.done",
            aoi_id=ctx.aoi_id,
            nodes=len(nodes),
            advanced=len(rows),
            with_chain=covered,
            day=target.isoformat(),
            forecast=target > today,
        )
        if covered == 0:
            # No chain anywhere: every cell will score dark and flagged. Worth
            # a warning, because the usual cause is that `limen fwi-backfill`
            # was never run for this AOI.
            log.warning("fwi_update.no_chain", aoi_id=ctx.aoi_id, day=target.isoformat())
        return ctx.with_update(fwi_nodes=tuple(nodes), fwi_by_node=tuple(chains))

    def _span(self, target: date, stored: list[StoredChain | None]) -> list[date]:
        """Every day some node still has to walk, earliest first.

        A node with no state at all walks the whole gap, so one cold node
        widens the window for the grid -- which is correct: the fetch is one
        request for every node and the extra days are free to the nodes that
        do not need them.
        """
        floor = target - timedelta(days=self._t.fwi.max_gap_days)
        if not stored or any(s is None for s in stored):
            first = floor
        else:
            first = min(max(s.day + timedelta(days=1), floor) for s in stored if s is not None)
        return [first + timedelta(days=i) for i in range((target - first).days + 1)]

    async def _observations(
        self, nodes: list[tuple[float, float]], days: list[date]
    ) -> list[dict[date, FireWeatherObservation]]:
        """The noon observations of ``days``, per node, on the FWI lattice.

        Deliberately its own fetch rather than a reuse of MeteoFetch's grid.
        Two reasons, and the second is the real one: that grid carries only
        precipitation, and it is anchored on the AOI bbox while the FWI
        lattice is global, so every node would be reading a neighbour's
        weather. One extra call per AOI per tick buys each node its own.

        The window starts a day early: the 24 h rain of a noon reading comes
        from the hours before it, which are in the previous calendar day.
        """
        window_start = datetime.combine(days[0] - timedelta(days=1), time.min, UTC)
        window_end = datetime.combine(days[-1], time.max, UTC)
        series = await self._client.get_fire_weather_grid(
            nodes=nodes,
            window_start=window_start,
            window_end=window_end,
            # The forecast API covers the recent past, today *and* the days
            # ahead — which is what makes the forecast sweep possible at all.
            # The archive lags days behind and would leave every live sweep
            # empty.
            use_archive=False,
        )
        out: list[dict[date, FireWeatherObservation]] = []
        for (lon, lat), samples in zip(nodes, series, strict=True):
            if not samples:
                out.append({})
                continue
            snapshot = MeteoSnapshot(
                centroid_lon=lon,
                centroid_lat=lat,
                window_start=window_start,
                window_end=window_end,
                samples=samples,
            )
            observed = {d: obs for d in days if (obs := snapshot.noon_observation(d)) is not None}
            out.append(observed)
        return out


__all__ = ["FwiUpdateExecutor"]
