"""``limen fwi-backfill`` — rebuild the recursive FWI chain from the archive.

The three moisture codes are recursive, so a chain started today from Van
Wagner's standard initial values says nothing about today: FFMC forgets in a
day, but DC has a ~52-day memory, and until it has been carried through that
many days of real weather it is still reporting its seed value. This command
walks the ERA5 archive day by day and builds the state up, so the first
operational sweep reads codes that mean something.

Work is per **weather node**, not per cell: the chain is a function of the
weather alone, and Open-Meteo serves it at ~9 km. A region's tens of
thousands of cells share a few dozen chains, and computing one per cell would
be the same arithmetic repeated ~500 times for an identical answer.

Idempotent: re-running a window recomputes each day from its true
predecessor and upserts, so overlapping runs converge rather than compound.

Env knobs, matching the other one-shot commands:

* ``LIMEN_FWI_AOI``  — one AOI id; absent ⇒ every seeded AOI.
* ``LIMEN_FWI_DAYS`` — days of history to rebuild (default 60, ≥ the DC memory).

The node spacing is **not** an env knob: it is the key of ``fwi_state``, so it
lives in ``wildfire.yaml`` where changing it is a visible decision.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from limen.core.logging import get_logger
from limen.core.models.hazard import HazardType
from limen.core.scoring.regional_thresholds import (
    WildfireThresholds,
    load_hazard_thresholds,
)
from limen.core.scoring.wildfire.fwi import FwiParams, FwiState, advance
from limen.data.db import acquire, lifespan_pool
from limen.data.repos import fwi_state_repo
from limen.data.repos.aoi_repo import list_aoi_ids
from limen.data.repos.fwi_state_repo import NodeDay
from limen.integrations._http import SharedHttpClient
from limen.integrations.openmeteo.client import OpenMeteoHttpClient
from limen.integrations.openmeteo.dtos import FireWeatherObservation, MeteoSnapshot
from limen.integrations.openmeteo.grid import build_snapped_nodes

log = get_logger(__name__)

_AOI_ENV = "LIMEN_FWI_AOI"
_DAYS_ENV = "LIMEN_FWI_DAYS"

#: Van Wagner's DC has a ~52-day time lag. Rebuilding less than that leaves
#: the drought code still carrying its seed value into production.
_DEFAULT_DAYS = 60


@dataclass(frozen=True, slots=True)
class BackfillResult:
    aoi_id: str
    nodes: int
    days_written: int
    #: The most recent day any node actually covered. The reanalysis archive
    #: lags real time by a few days and the lag moves, so the requested end
    #: and the achieved end are different facts and both are reported.
    last_day: date | None = None


def params_from(thresholds: WildfireThresholds) -> FwiParams:
    """The FWI parameters a hazard configuration declares."""
    return FwiParams(
        ffmc_start=thresholds.fwi.ffmc_start,
        dmc_start=thresholds.fwi.dmc_start,
        dc_start=thresholds.fwi.dc_start,
        day_length_dmc=thresholds.fwi.day_length_dmc,
        day_length_dc=thresholds.fwi.day_length_dc,
    )


async def _aoi_bbox(aoi_id: str) -> tuple[float, float, float, float] | None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT ST_XMin(geom) AS x0, ST_YMin(geom) AS y0,
                   ST_XMax(geom) AS x1, ST_YMax(geom) AS y1
              FROM aoi WHERE id = $1
            """,
            aoi_id,
        )
    if row is None:
        return None
    return (float(row["x0"]), float(row["y0"]), float(row["x1"]), float(row["y1"]))


def _observations(snapshot: MeteoSnapshot, days: list[date]) -> dict[date, FireWeatherObservation]:
    out: dict[date, FireWeatherObservation] = {}
    for day in days:
        obs = snapshot.noon_observation(day)
        if obs is not None:
            out[day] = obs
    return out


async def advance_node(
    *,
    lon: float,
    lat: float,
    observations: dict[date, FireWeatherObservation],
    days: list[date],
    params: FwiParams,
    max_gap_days: int,
) -> list[NodeDay]:
    """Walk one node's chain over ``days``, returning the rows to write.

    Starts from the stored state before the window when there is one, so a
    second run extends the chain instead of restarting it. A day with no
    observation is **skipped, not zeroed**: inventing a reading would inject
    a fake drying day that the recursion would carry for weeks.

    A stored state older than ``max_gap_days`` is discarded. Carrying a
    drought code across three weeks of missing weather as if the days were
    consecutive produces a number with no history behind it, and
    ``chain_days`` would keep climbing until ``spinup`` called the broken
    chain settled.
    """
    stored = await fwi_state_repo.latest_before(lon, lat, days[0])
    if stored is not None and (days[0] - stored.day).days > max_gap_days:
        log.warning(
            "fwi.chain.gap_too_long",
            lon=lon,
            lat=lat,
            last_day=stored.day.isoformat(),
            resuming_at=days[0].isoformat(),
            gap_days=(days[0] - stored.day).days,
            max_gap_days=max_gap_days,
        )
        stored = None
    state: FwiState = stored.state if stored else params.initial_state
    chain_days = stored.chain_days if stored else 0

    out: list[NodeDay] = []
    for day in days:
        obs = observations.get(day)
        if obs is None:
            continue
        outputs = advance(
            state,
            month=day.month,
            temperature_c=obs.temperature_c,
            relative_humidity_pct=obs.relative_humidity_pct,
            wind_speed_kmh=obs.wind_speed_kmh,
            rain_24h_mm=obs.rain_24h_mm,
            params=params,
        )
        chain_days += 1
        out.append(
            NodeDay(
                lon=lon,
                lat=lat,
                day=day,
                outputs=outputs,
                chain_days=chain_days,
                temperature_c=obs.temperature_c,
                relative_humidity_pct=obs.relative_humidity_pct,
                wind_speed_kmh=obs.wind_speed_kmh,
                rain_24h_mm=obs.rain_24h_mm,
            )
        )
        state = outputs.state
    return out


async def backfill_aoi(
    *,
    aoi_id: str,
    days_back: int,
    thresholds: WildfireThresholds,
    client: OpenMeteoHttpClient,
    end: date | None = None,
) -> BackfillResult:
    """Rebuild every weather node's chain over one AOI's trailing window."""
    bbox = await _aoi_bbox(aoi_id)
    if bbox is None:
        log.warning("fwi.backfill.skip", aoi_id=aoi_id, reason="unknown aoi")
        return BackfillResult(aoi_id=aoi_id, nodes=0, days_written=0)

    # The reanalysis archive lags roughly a day behind real time.
    last = end or (datetime.now(UTC).date() - timedelta(days=1))
    first = last - timedelta(days=days_back - 1)
    days = [first + timedelta(days=i) for i in range(days_back)]

    nodes = build_snapped_nodes(bbox, spacing=thresholds.fwi.node_spacing_deg)
    # One day of margin before the window: the 24 h rain of the first day is
    # drawn from the hours preceding its noon, which are in the day before.
    series = await client.get_fire_weather_grid(
        nodes=nodes,
        window_start=datetime.combine(first - timedelta(days=1), datetime.min.time(), UTC),
        window_end=datetime.combine(last, datetime.max.time(), UTC),
        use_archive=True,
    )

    params = params_from(thresholds)
    rows: list[NodeDay] = []
    for (lon, lat), samples in zip(nodes, series, strict=True):
        observations = _observations(
            MeteoSnapshot(
                centroid_lon=lon,
                centroid_lat=lat,
                window_start=datetime.combine(first, datetime.min.time(), UTC),
                window_end=datetime.combine(last, datetime.max.time(), UTC),
                samples=samples,
            ),
            days,
        )
        if not observations:
            continue
        rows.extend(
            await advance_node(
                lon=lon,
                lat=lat,
                observations=observations,
                days=days,
                params=params,
                max_gap_days=thresholds.fwi.max_gap_days,
            )
        )

    if not rows:
        # Every node degraded. Writing nothing is right: a chain built from no
        # weather would be indistinguishable from a real one.
        log.warning("fwi.backfill.no_weather", aoi_id=aoi_id, nodes=len(nodes))
        return BackfillResult(aoi_id=aoi_id, nodes=len(nodes), days_written=0)

    written = await fwi_state_repo.upsert_many(rows)
    covered = max(r.day for r in rows)
    lag = (last - covered).days
    if lag > 0:
        # Not an error: the reanalysis archive is behind real time by a few
        # days and the lag moves. Saying how far behind the chain actually
        # ends beats a silent gap that the next run would then treat as an
        # interruption.
        log.warning(
            "fwi.backfill.archive_lag",
            aoi_id=aoi_id,
            requested_end=last.isoformat(),
            covered_to=covered.isoformat(),
            lag_days=lag,
        )
    log.info(
        "fwi.backfill.aoi.done",
        aoi_id=aoi_id,
        nodes=len(nodes),
        days=days_back,
        days_written=written,
        covered_to=covered.isoformat(),
    )
    return BackfillResult(aoi_id=aoi_id, nodes=len(nodes), days_written=written, last_day=covered)


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        log.warning("fwi.backfill.bad_env", var=name, value=raw, using=default)
        return default


async def run() -> int:
    days_back = max(_int_env(_DAYS_ENV, _DEFAULT_DAYS), 1)
    loaded = load_hazard_thresholds(HazardType.WILDFIRE)
    if not isinstance(loaded, WildfireThresholds):
        log.error("fwi.backfill.bad_config", got=type(loaded).__name__)
        return 1

    client = OpenMeteoHttpClient()
    async with lifespan_pool():
        one = os.getenv(_AOI_ENV)
        aoi_ids = [one] if one else await list_aoi_ids()
        if not aoi_ids:
            log.warning("fwi.backfill.no_aoi")
            return 0
        for aoi_id in aoi_ids:
            await backfill_aoi(aoi_id=aoi_id, days_back=days_back, thresholds=loaded, client=client)
    await SharedHttpClient.aclose()
    return 0


__all__ = ["BackfillResult", "advance_node", "backfill_aoi", "params_from", "run"]
