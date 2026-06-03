"""``limen backtest`` — replay historical events and score §2.5 metrics.

For an AOI + time window:

1. Pull IFFI features whose ``occurrence_date`` falls inside the
   window — these are the **truth set** (one positive per cell-day
   that hosts a recorded landslide).
2. Fetch Open-Meteo historical (ERA5) precipitation for the AOI bbox
   covering ``[start - 48 h, end]`` so the engine sees the antecedent
   rain.
3. For each hour from ``start`` to ``end``, assemble a thin bundle per
   cell (static factors from DB + a rainfall slice up to the
   evaluation time) and call :class:`MultiFactorScoringEngine`.
4. A cell-hour is a **hit** iff the engine flags it ``High`` or
   ``VeryHigh`` within ``lead_time_hours_min`` hours before a recorded
   IFFI event in the same cell; **false alarm** if a high score is not
   followed by an event in the same lookahead window; **lead time** is
   the average hours-ahead of the earliest high score before each hit.
5. Write a short Markdown report.

Configuration knobs (env vars, kept off the dispatcher for parity with
``limen calibrate``):

* ``LIMEN_BACKTEST_AOI``         — single AOI id to backtest (default:
  every seeded AOI).
* ``LIMEN_BACKTEST_START`` /
  ``LIMEN_BACKTEST_END``           — ISO datetimes; default Oct 2018
  Southern-Italy storm window.
* ``LIMEN_BACKTEST_HIGH_LEVEL``  — minimum :class:`RiskLevel` to count as
  alert (default ``High``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from limen.core.logging import get_logger
from limen.core.models.risk import (
    CellFeatureBundle,
    DynamicInputs,
    RainfallSample,
    RainfallSeries,
    RiskLevel,
    StaticFactors,
)
from limen.core.scoring.engine import MultiFactorScoringEngine
from limen.core.scoring.regional_thresholds import load_regional_thresholds
from limen.data.db import acquire, close_pool, init_pool
from limen.data.migrate import run_migrations
from limen.data.repos.aoi_repo import get_aoi, list_aoi_ids
from limen.integrations._http import SharedHttpClient
from limen.integrations.openmeteo.client import OpenMeteoHttpClient

log = get_logger(__name__)

REPORTS_DIR = Path("./reports")
_DEFAULT_START = datetime(2018, 10, 28, 0, 0, tzinfo=UTC)
_DEFAULT_END = datetime(2018, 11, 2, 0, 0, tzinfo=UTC)
_ALERT_LEVELS_ORDERED = (
    RiskLevel.None_,
    RiskLevel.Low,
    RiskLevel.Moderate,
    RiskLevel.High,
    RiskLevel.VeryHigh,
)


@dataclass(frozen=True, slots=True)
class _BacktestMetrics:
    aoi_id: str
    truth_events: int
    alerts_total: int
    hits: int
    false_alarms: int
    misses: int
    hit_rate: float
    far: float
    mean_lead_hours: float
    report_path: Path


# ---------------------------------------------------------------------------
# Data fetchers
# ---------------------------------------------------------------------------
async def _fetch_truth_events(
    aoi_id: str,
    *,
    start: datetime,
    end: datetime,
) -> dict[str, datetime]:
    """Return ``{cell_id: occurrence_datetime}`` from IFFI features that
    occurred in ``[start, end]`` inside ``aoi_id``."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT g.id AS cell_id, MIN(i.occurrence_date) AS first_event
            FROM iffi_landslides i
            JOIN grid_cells g
              ON ST_Intersects(g.geom, i.geom)
            WHERE g.aoi_id = $1
              AND i.occurrence_date >= $2::date
              AND i.occurrence_date <= $3::date
            GROUP BY g.id
            """,
            aoi_id,
            start.date(),
            end.date(),
        )
    out: dict[str, datetime] = {}
    for r in rows:
        d: date = r["first_event"]
        # Anchor to the middle of the day in UTC — IFFI rarely has hour-precision.
        out[str(r["cell_id"])] = datetime(d.year, d.month, d.day, 12, 0, tzinfo=UTC)
    return out


async def _fetch_static_factors(aoi_id: str) -> list[StaticFactors]:
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT c.cell_id, c.iffi_density_500, c.slope_deg, c.pai_class_norm,
                   c.litho_weight, c.s_static
            FROM cell_static_factors c
            JOIN grid_cells g ON g.id = c.cell_id
            WHERE g.aoi_id = $1
            """,
            aoi_id,
        )
    out: list[StaticFactors] = []
    for r in rows:
        out.append(
            StaticFactors(
                cell_id=str(r["cell_id"]),
                iffi_density_500=(
                    float(r["iffi_density_500"]) if r["iffi_density_500"] is not None else None
                ),
                slope_deg=float(r["slope_deg"]) if r["slope_deg"] is not None else None,
                pai_class_norm=(
                    float(r["pai_class_norm"]) if r["pai_class_norm"] is not None else None
                ),
                litho_weight=float(r["litho_weight"]) if r["litho_weight"] is not None else None,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Bundle assembly + metrics
# ---------------------------------------------------------------------------
def _level_at_least(level: RiskLevel, threshold: RiskLevel) -> bool:
    return _ALERT_LEVELS_ORDERED.index(level) >= _ALERT_LEVELS_ORDERED.index(threshold)


def _hourly_window(start: datetime, end: datetime) -> list[datetime]:
    out: list[datetime] = []
    t = start
    while t <= end:
        out.append(t)
        t += timedelta(hours=1)
    return out


def _synthesise_rainfall(
    *,
    samples: list[RainfallSample],
    as_of: datetime,
    window_hours: int = 48,
) -> RainfallSeries:
    """Slice the master rainfall series up to ``as_of`` (last ``window_hours``)."""
    cutoff = as_of - timedelta(hours=window_hours)
    sliced = tuple(s for s in samples if cutoff <= s.timestamp <= as_of)
    return RainfallSeries(samples=sliced)


def _evaluate(
    *,
    aoi_id: str,
    cells: list[StaticFactors],
    truth: dict[str, datetime],
    rainfall: list[RainfallSample],
    start: datetime,
    end: datetime,
    alert_level: RiskLevel,
    lead_min_hours: float,
) -> _BacktestMetrics:
    thresholds = load_regional_thresholds()
    engine = MultiFactorScoringEngine(thresholds)
    hours = _hourly_window(start, end)

    earliest_alert: dict[str, datetime] = {}
    alerts_total = 0
    for t in hours:
        rainfall_slice = _synthesise_rainfall(samples=rainfall, as_of=t)
        for sf in cells:
            bundle = CellFeatureBundle(
                aoi_id=aoi_id,
                cell_id=sf.cell_id,
                static=sf,
                dynamic=DynamicInputs(valuation_time=t, rainfall=rainfall_slice),
            )
            scored = engine.score(bundle)
            if _level_at_least(scored.level, alert_level):
                alerts_total += 1
                if sf.cell_id not in earliest_alert:
                    earliest_alert[sf.cell_id] = t

    hits = 0
    misses = 0
    leads: list[float] = []
    for cell_id, event_time in truth.items():
        alert_time = earliest_alert.get(cell_id)
        if alert_time is None:
            misses += 1
            continue
        lead_hours = (event_time - alert_time).total_seconds() / 3600.0
        if 0 < lead_hours <= max(lead_min_hours, 24.0):
            hits += 1
            leads.append(lead_hours)
        else:
            misses += 1

    false_alarms = max(0, len(earliest_alert) - hits)
    hit_rate = hits / len(truth) if truth else 0.0
    far = false_alarms / (hits + false_alarms) if (hits + false_alarms) else 0.0
    mean_lead = sum(leads) / len(leads) if leads else 0.0

    report = _write_report(
        aoi_id=aoi_id,
        start=start,
        end=end,
        cells_scored=len(cells),
        truth_events=len(truth),
        alerts_total=alerts_total,
        hits=hits,
        false_alarms=false_alarms,
        misses=misses,
        hit_rate=hit_rate,
        far=far,
        mean_lead=mean_lead,
        thresholds_hit_min=thresholds.calibration.backtest.hit_rate_min,
        thresholds_far_max=thresholds.calibration.backtest.far_max,
        thresholds_lead_min=thresholds.calibration.backtest.lead_time_hours_min,
    )

    return _BacktestMetrics(
        aoi_id=aoi_id,
        truth_events=len(truth),
        alerts_total=alerts_total,
        hits=hits,
        false_alarms=false_alarms,
        misses=misses,
        hit_rate=hit_rate,
        far=far,
        mean_lead_hours=mean_lead,
        report_path=report,
    )


def _write_report(
    *,
    aoi_id: str,
    start: datetime,
    end: datetime,
    cells_scored: int,
    truth_events: int,
    alerts_total: int,
    hits: int,
    false_alarms: int,
    misses: int,
    hit_rate: float,
    far: float,
    mean_lead: float,
    thresholds_hit_min: float,
    thresholds_far_max: float,
    thresholds_lead_min: float,
) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"backtest_{aoi_id}_{start.date()}_{end.date()}.md"
    pass_hit = "PASS" if hit_rate >= thresholds_hit_min else "FAIL"
    pass_far = "PASS" if far <= thresholds_far_max else "FAIL"
    pass_lead = "PASS" if mean_lead >= thresholds_lead_min else "FAIL"

    lines = [
        f"# Limen backtest report — AOI `{aoi_id}`",
        "",
        f"Window: **{start.isoformat()} → {end.isoformat()}**",
        f"Generated: {datetime.now(UTC).isoformat()}",
        "",
        f"- Cells scored per hour: **{cells_scored}**",
        f"- Truth events (IFFI in window): **{truth_events}**",
        f"- Alert-level cell-hours: **{alerts_total}**",
        f"- Hits: **{hits}**, false alarms: **{false_alarms}**, misses: **{misses}**",
        "",
        "## §2.5 metrics",
        "",
        f"- **Hit rate**: {hit_rate:.2%} (target ≥ {thresholds_hit_min:.0%}) — **{pass_hit}**",
        f"- **FAR**: {far:.2%} (target ≤ {thresholds_far_max:.0%}) — **{pass_far}**",
        f"- **Mean lead time**: {mean_lead:.1f} h "
        f"(target ≥ {thresholds_lead_min:.0f} h) — **{pass_lead}**",
        "",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# Open-Meteo historical fetch (single call per AOI)
# ---------------------------------------------------------------------------
async def _fetch_rainfall_for_window(
    *,
    aoi_id: str,
    bbox: tuple[float, float, float, float],
    start: datetime,
    end: datetime,
) -> list[RainfallSample]:
    client = OpenMeteoHttpClient()
    snap = await client.get_meteo_snapshot(
        aoi_id=aoi_id,
        bbox=bbox,
        window_start=start - timedelta(hours=48),
        window_end=end,
    )
    if snap is None:
        log.warning("backtest.rainfall.degraded", aoi_id=aoi_id)
        return []
    return [
        RainfallSample(timestamp=s.timestamp, precipitation_mm=s.precipitation_mm)
        for s in snap.samples
    ]


# ---------------------------------------------------------------------------
# CLI runner
# ---------------------------------------------------------------------------
def _parse_dt(env_name: str, default: datetime) -> datetime:
    raw = os.getenv(env_name)
    if not raw:
        return default
    return datetime.fromisoformat(raw)


def _parse_level(env_name: str, default: RiskLevel) -> RiskLevel:
    raw = os.getenv(env_name)
    if not raw:
        return default
    try:
        return RiskLevel(raw)
    except ValueError:
        log.warning("backtest.bad_level", value=raw)
        return default


async def run() -> int:
    """Run backtest for the configured AOI(s) and window."""
    start = _parse_dt("LIMEN_BACKTEST_START", _DEFAULT_START)
    end = _parse_dt("LIMEN_BACKTEST_END", _DEFAULT_END)
    alert_level = _parse_level("LIMEN_BACKTEST_HIGH_LEVEL", RiskLevel.High)
    single_aoi = os.getenv("LIMEN_BACKTEST_AOI")

    await init_pool()
    try:
        await run_migrations()
        thresholds = load_regional_thresholds()
        aois = [single_aoi] if single_aoi else await list_aoi_ids()
        if not aois:
            log.warning("backtest.no_aois", note="run `limen seed` first")
            return 0

        for aoi_id in aois:
            aoi = await get_aoi(aoi_id)
            if aoi is None:
                log.warning("backtest.aoi.missing", aoi_id=aoi_id)
                continue
            bbox = tuple(aoi.bbox.bounds)
            assert len(bbox) == 4

            cells = await _fetch_static_factors(aoi_id)
            truth = await _fetch_truth_events(aoi_id, start=start, end=end)
            rainfall = await _fetch_rainfall_for_window(
                aoi_id=aoi_id, bbox=bbox, start=start, end=end
            )
            log.info(
                "backtest.aoi.loaded",
                aoi_id=aoi_id,
                cells=len(cells),
                truth_events=len(truth),
                rainfall_samples=len(rainfall),
            )

            metrics = _evaluate(
                aoi_id=aoi_id,
                cells=cells,
                truth=truth,
                rainfall=rainfall,
                start=start,
                end=end,
                alert_level=alert_level,
                lead_min_hours=thresholds.calibration.backtest.lead_time_hours_min,
            )
            log.info(
                "backtest.aoi.done",
                aoi_id=metrics.aoi_id,
                hit_rate=metrics.hit_rate,
                far=metrics.far,
                mean_lead_hours=metrics.mean_lead_hours,
                report=str(metrics.report_path),
            )
    finally:
        await SharedHttpClient.aclose()
        await close_pool()
    return 0


def main() -> int:
    import asyncio

    return asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
