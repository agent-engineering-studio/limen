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
from limen.data.repos.fwi_state_repo import NodeDay
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

        params = params_from(self._t)
        rows: list[NodeDay] = []
        chains: list[FireWeatherState | None] = []
        # One fetch for the whole grid, covering the widest span any node can
        # need plus the day before it (the 24 h rain of the first noon).
        observations = await self._observations(nodes, self._span(target, self._t.fwi.max_gap_days))
        for (lon, lat), by_day in zip(nodes, observations, strict=True):
            stored = await fwi_state_repo.latest_before(lon, lat, target)
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

    @staticmethod
    def _span(target: date, max_gap_days: int) -> list[date]:
        """Every day any node might need, widest case first."""
        first = target - timedelta(days=max_gap_days)
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
