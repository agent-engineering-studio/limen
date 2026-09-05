"""Advance the FWI chain for the AOI's weather nodes (#62).

The step between "what the weather is" and "what that means for fire". It
reads the meteo the shared MeteoFetch already pulled, takes each node's noon
observation, advances the recursive codes from the state on disk, writes the
new day, and puts the result on the context so the assembler can hand each
cell the chain of its nearest node.

It runs **before** scoring and only in the wildfire workflow: the chain has
no meaning for a slope, and stepping it in the landslide sweep would burn a
write per node per tick for nothing.

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
            raise TypeError(
                f"FwiUpdate needs WildfireThresholds, got {type(loaded).__name__}"
            )
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
        day = ctx.valuation_time.date()

        observations = await self._observations(nodes, day)
        rows: list[NodeDay] = []
        params = params_from(self._t)
        for (lon, lat), obs in zip(nodes, observations, strict=True):
            if obs is None:
                continue
            rows.extend(
                await advance_node(
                    lon=lon,
                    lat=lat,
                    observations={day: obs},
                    days=[day],
                    params=params,
                    max_gap_days=self._t.fwi.max_gap_days,
                )
            )
        if rows:
            await fwi_state_repo.upsert_many(rows)

        chains = await fwi_state_repo.read_day(nodes, day)
        covered = sum(1 for c in chains if c is not None)
        log.info(
            "fwi_update.done",
            aoi_id=ctx.aoi_id,
            nodes=len(nodes),
            advanced=len(rows),
            with_chain=covered,
            day=day.isoformat(),
        )
        if covered == 0:
            # No chain anywhere: every cell will score dark and flagged. Worth
            # a warning, because the usual cause is that `limen fwi-backfill`
            # was never run for this AOI.
            log.warning("fwi_update.no_chain", aoi_id=ctx.aoi_id, day=day.isoformat())
        return ctx.with_update(fwi_nodes=tuple(nodes), fwi_by_node=tuple(chains))

    async def _observations(
        self, nodes: list[tuple[float, float]], day: date
    ) -> list[FireWeatherObservation | None]:
        """One noon observation per node, fetched on the FWI lattice.

        Deliberately its own fetch rather than a reuse of MeteoFetch's grid.
        Two reasons, and the second is the real one: that grid carries only
        precipitation, and it is anchored on the AOI bbox while the FWI
        lattice is global, so every node would be reading a neighbour's
        weather. One extra call per AOI per tick buys each node its own.

        The window starts a day early: the 24 h rain of a noon reading comes
        from the hours before it, which are in the previous calendar day.
        """
        window_start = datetime.combine(day - timedelta(days=1), time.min, UTC)
        window_end = datetime.combine(day, time.max, UTC)
        series = await self._client.get_fire_weather_grid(
            nodes=nodes,
            window_start=window_start,
            window_end=window_end,
            # The forecast API covers the recent past and today; the archive
            # lags days behind and would leave every live sweep empty.
            use_archive=False,
        )
        out: list[FireWeatherObservation | None] = []
        for (lon, lat), samples in zip(nodes, series, strict=True):
            if not samples:
                out.append(None)
                continue
            snapshot = MeteoSnapshot(
                centroid_lon=lon,
                centroid_lat=lat,
                window_start=window_start,
                window_end=window_end,
                samples=samples,
            )
            out.append(snapshot.noon_observation(day))
        return out


__all__ = ["FwiUpdateExecutor"]
