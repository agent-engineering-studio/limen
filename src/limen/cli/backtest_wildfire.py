"""``limen backtest-wildfire`` — replay the FWI chain against EFFIS perimeters.

The §2.5 question, asked of fire: **in the 72 h before a burnt area started
burning, was that cell already at High or above?** Hits, false alarms and
lead time come out the same shape as the landslide backtest, so the two
reports can be read side by side.

Structurally a different replay, though, and deliberately not a
generalisation of the landslide one. That replay synthesises antecedent
rainfall hour by hour and re-scores every cell; the fire chain is *daily* and
*recursive*, so the replay walks a node's codes forward through the archive
exactly as the operational step does. Forcing the two through one function
would make both harder to read than either is alone.

Truth is ``fire_perimeters`` — the EFFIS burnt areas Limen ingests. The
service is public and needs no credentials; an un-ingested deployment still
gets an honest empty report rather than a crash.

The report pairs the hit rate with the **base rate**: the share of days a
burnt cell was in alert anyway. Without it the hit rate is unreadable,
because a model that calls every summer day dangerous maximises it while
discriminating nothing. Measured on Basilicata against real perimeters: 79 %
against a 43 % base in 2025, 100 % against 28 % in 2024.

Env knobs:

* ``LIMEN_BACKTEST_WILDFIRE_AOI``   — one AOI id; absent ⇒ every seeded AOI.
* ``LIMEN_BACKTEST_WILDFIRE_START`` / ``_END`` — ISO dates bounding the replay.
* ``LIMEN_BACKTEST_WILDFIRE_LEVEL`` — alert level counted as a warning
  (default ``High``, the EFFIS "high danger" band).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from limen.cli.fwi_backfill import params_from
from limen.core.logging import get_logger
from limen.core.models.hazard import HazardType
from limen.core.models.risk import (
    CellFeatureBundle,
    DynamicInputs,
    FireWeatherState,
    RiskLevel,
    StaticFactors,
)
from limen.core.scoring.regional_thresholds import (
    WildfireThresholds,
    load_hazard_thresholds,
)
from limen.core.scoring.wildfire import WildfireScoringEngine
from limen.core.scoring.wildfire.fwi import FwiState, advance
from limen.data.db import acquire, lifespan_pool
from limen.data.repos.aoi_repo import list_aoi_ids
from limen.integrations._http import SharedHttpClient
from limen.integrations.openmeteo.client import OpenMeteoHttpClient
from limen.integrations.openmeteo.dtos import MeteoSnapshot
from limen.integrations.openmeteo.grid import build_snapped_nodes, nearest_node

log = get_logger(__name__)

REPORTS_DIR = Path("reports")

_AOI_ENV = "LIMEN_BACKTEST_WILDFIRE_AOI"
_START_ENV = "LIMEN_BACKTEST_WILDFIRE_START"
_END_ENV = "LIMEN_BACKTEST_WILDFIRE_END"
_LEVEL_ENV = "LIMEN_BACKTEST_WILDFIRE_LEVEL"

#: The issue's question is about the three days before ignition. Fire danger
#: is a daily index, so a warning further back than this is not early warning
#: any more -- it is the summer being hot.
_LEAD_MAX_HOURS = 72.0

_LEVEL_ORDER = (
    RiskLevel.None_,
    RiskLevel.Low,
    RiskLevel.Moderate,
    RiskLevel.High,
    RiskLevel.VeryHigh,
)


@dataclass(frozen=True, slots=True)
class WildfireBacktestMetrics:
    aoi_id: str
    truth_fires: int
    cells_warned: int
    hits: int
    false_alarms: int
    misses: int
    hit_rate: float
    far: float
    mean_lead_hours: float
    #: Quota di giornate della finestra in cui una cella poi bruciata era
    #: comunque in allerta. È il metro dell'hit rate: un modello che dice
    #: "pericolo alto" tutti i giorni d'estate ottiene un hit rate altissimo
    #: senza discriminare nulla, e senza questo numero il report lo
    #: presenterebbe come bravura.
    base_rate: float
    report_path: Path | None


def _at_least(level: RiskLevel, threshold: RiskLevel) -> bool:
    return _LEVEL_ORDER.index(level) >= _LEVEL_ORDER.index(threshold)


async def fetch_burnt_cells(
    aoi_id: str, *, start: date, end: date
) -> dict[str, tuple[date, float, float]]:
    """``{cell_id: (fire_date, lon, lat)}`` for cells inside a burnt perimeter.

    The earliest fire per cell is the anchor: a cell that burned twice in the
    window is one truth event, not two, or a single well-warned area would
    inflate the hit rate by however often it caught fire.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT g.id AS cell_id,
                   MIN(p.fire_date) AS first_fire,
                   ST_X(ST_Centroid(g.geom)) AS lon,
                   ST_Y(ST_Centroid(g.geom)) AS lat
            FROM fire_perimeters p
            JOIN grid_cells g ON ST_Intersects(g.geom, p.geom)
            WHERE g.aoi_id = $1
              AND p.fire_date IS NOT NULL
              AND p.fire_date >= $2
              AND p.fire_date <= $3
            GROUP BY g.id, g.geom
            """,
            aoi_id,
            start,
            end,
        )
    return {str(r["cell_id"]): (r["first_fire"], float(r["lon"]), float(r["lat"])) for r in rows}


async def _static_by_cell(cell_ids: list[str]) -> dict[str, StaticFactors]:
    if not cell_ids:
        return {}
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT cell_id, landuse_code, slope_deg
            FROM cell_static_factors
            WHERE cell_id = ANY($1::text[])
            """,
            cell_ids,
        )
    return {
        str(r["cell_id"]): StaticFactors(
            cell_id=str(r["cell_id"]),
            landuse_code=r["landuse_code"],
            slope_deg=r["slope_deg"],
        )
        for r in rows
    }


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


def replay_chain(
    *,
    snapshot: MeteoSnapshot,
    days: list[date],
    thresholds: WildfireThresholds,
) -> dict[date, FireWeatherState]:
    """Walk one node's chain across ``days``, from the seed.

    From the seed rather than from ``fwi_state``: a backtest must not read the
    operational state, or a replay of last summer would start from today's
    drought code. Days without an observation are skipped, exactly as the
    live step skips them.
    """
    params = params_from(thresholds)
    state = FwiState(ffmc=params.ffmc_start, dmc=params.dmc_start, dc=params.dc_start)
    chain_days = 0
    out: dict[date, FireWeatherState] = {}
    for day in days:
        obs = snapshot.noon_observation(day)
        if obs is None:
            continue
        step = advance(
            state,
            month=day.month,
            temperature_c=obs.temperature_c,
            relative_humidity_pct=obs.relative_humidity_pct,
            wind_speed_kmh=obs.wind_speed_kmh,
            rain_24h_mm=obs.rain_24h_mm,
            params=params,
        )
        chain_days += 1
        out[day] = FireWeatherState(
            day=day,
            ffmc=step.state.ffmc,
            dmc=step.state.dmc,
            dc=step.state.dc,
            isi=step.isi,
            bui=step.bui,
            fwi=step.fwi,
            chain_days=chain_days,
        )
        state = step.state
    return out


def evaluate(
    *,
    aoi_id: str,
    truth: dict[str, tuple[date, float, float]],
    static: dict[str, StaticFactors],
    nodes: list[tuple[float, float]],
    chains: list[dict[date, FireWeatherState]],
    days: list[date],
    thresholds: WildfireThresholds,
    alert_level: RiskLevel,
    season: tuple[date, date] | None = None,
) -> WildfireBacktestMetrics:
    """Score every burnt cell across the window and measure the warning.

    Only the burnt cells are scored, not the whole grid, and only across the
    lead horizon before each fire. That bounds what can be claimed: hit rate
    and lead time are honest, the **false-alarm rate is not measured at all**
    and is reported as zero, because a false alarm is by definition a warning
    on ground that did not burn — and this replay never looks at such ground.
    A real FAR needs the whole AOI replayed across the season, which is a much
    heavier job; the report says so rather than printing a flattering number.
    """
    engine = WildfireScoringEngine(thresholds)
    horizon_days = int(_LEAD_MAX_HOURS // 24)
    scored_days = set(days)

    def alerted(cell_id: str, sf: StaticFactors, fw: FireWeatherState, day: date) -> bool:
        scored = engine.score(
            CellFeatureBundle(
                aoi_id=aoi_id,
                cell_id=cell_id,
                static=sf,
                dynamic=DynamicInputs(
                    valuation_time=datetime.combine(day, time(12), UTC),
                    fire_weather=fw,
                ),
            )
        )
        return _at_least(scored.level, alert_level)

    # Il tasso di base si misura sulla **stagione degli incendi**, non sui
    # giorni di spin-up che la precedono: quelli sono primavera, il pericolo è
    # basso, e includerli abbasserebbe il metro gonfiando la discriminazione.
    first, last = season or (days[0], days[-1])
    base_days = 0
    base_alerted = 0

    hits = 0
    misses = 0
    warned_cells = 0
    leads: list[float] = []
    for cell_id, (fire_date, lon, lat) in truth.items():
        chain = chains[nearest_node(lon, lat, nodes)]
        sf = static.get(cell_id) or StaticFactors(cell_id=cell_id)
        # Solo i giorni dentro l'orizzonte di preavviso, dal più lontano al
        # giorno stesso. Scandire l'intera finestra prenderebbe la prima
        # allerta della *stagione*: con la finestra di default (400 giorni)
        # ogni incendio risulterebbe allertato un anno prima, cioè mancato e
        # falso allarme insieme, e il report direbbe 0% di hit rate qualunque
        # sia la bravura del modello.
        window = [
            fire_date - timedelta(days=d)
            for d in range(horizon_days, -1, -1)
            if (fire_date - timedelta(days=d)) in scored_days
        ]
        # Il metro: quanto spesso questa cella sarebbe stata in allerta in un
        # giorno qualunque della finestra, non solo prima del suo incendio.
        for day in days:
            if not first <= day <= last:
                continue
            fw = chain.get(day)
            if fw is None:
                continue
            base_days += 1
            if alerted(cell_id, sf, fw, day):
                base_alerted += 1

        earliest: date | None = None
        for day in window:
            fw = chain.get(day)
            if fw is None:
                continue
            if alerted(cell_id, sf, fw, day):
                earliest = day
                break
        if earliest is None:
            misses += 1
            continue
        warned_cells += 1
        hits += 1
        leads.append((fire_date - earliest).days * 24.0)

    # Un'allerta dentro l'orizzonte è per costruzione un hit, quindi qui i
    # falsi allarmi sono sempre zero: contarli richiede di rigiocare le celle
    # che *non* hanno bruciato, che è il limite dichiarato nel report.
    false_alarms = 0
    hit_rate = hits / len(truth) if truth else 0.0
    far = false_alarms / (hits + false_alarms) if (hits + false_alarms) else 0.0
    mean_lead = sum(leads) / len(leads) if leads else 0.0

    return WildfireBacktestMetrics(
        aoi_id=aoi_id,
        truth_fires=len(truth),
        cells_warned=warned_cells,
        hits=hits,
        false_alarms=false_alarms,
        misses=misses,
        hit_rate=hit_rate,
        far=far,
        mean_lead_hours=mean_lead,
        base_rate=base_alerted / base_days if base_days else 0.0,
        report_path=None,
    )


def _lift(metrics: WildfireBacktestMetrics) -> float:
    """Quante volte l'hit rate supera il tasso di base. 0 se non misurabile."""
    return metrics.hit_rate / metrics.base_rate if metrics.base_rate > 0 else 0.0


def write_report(
    metrics: WildfireBacktestMetrics, *, start: date, end: date, alert_level: RiskLevel
) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"backtest_wildfire_{metrics.aoi_id}_{start}_{end}.md"
    lines = [
        f"# Limen backtest incendio — AOI `{metrics.aoi_id}`",
        "",
        f"Finestra: **{start} → {end}**",
        f"Generato: {datetime.now(UTC).isoformat()}",
        f"Soglia di allerta: **{alert_level.value}**, "
        f"orizzonte di preavviso **{_LEAD_MAX_HOURS:.0f} h**",
        "",
        f"- Celle bruciate (perimetri EFFIS nella finestra): **{metrics.truth_fires}**",
        f"- Celle con almeno un'allerta: **{metrics.cells_warned}**",
        f"- Hit: **{metrics.hits}**, falsi allarmi: **{metrics.false_alarms}**, "
        f"mancati: **{metrics.misses}**",
        "",
        "## Metriche §2.5",
        "",
        f"- **Hit rate**: {metrics.hit_rate:.2%}",
        f"- **Tasso di base**: {metrics.base_rate:.2%} "
        f"(quota di giornate in allerta a prescindere dagli incendi)",
        f"- **Discriminazione**: {_lift(metrics):.2f} volte il tasso di base",
        "- **FAR**: non misurato (vedi nota)",
        f"- **Preavviso medio**: {metrics.mean_lead_hours:.1f} h",
        "",
        "> L'hit rate da solo non dice nulla: un modello che dichiara pericolo",
        "> alto tutti i giorni d'estate lo massimizza senza discriminare. Il",
        "> confronto con il tasso di base è ciò che separa la bravura dalla",
        "> frequenza — sotto 1.0 il modello è peggio del caso.",
        "> Il replay guarda solo le celle che hanno bruciato, e solo",
        f"> l'orizzonte di {_LEAD_MAX_HOURS:.0f} h prima di ciascun incendio. Hit rate e",
        "> preavviso sono quindi misurati; il **FAR no**: un falso allarme è",
        "> per definizione un'allerta su terreno che non ha preso fuoco, e qui",
        "> quel terreno non viene mai valutato. Misurarlo richiede di rigiocare",
        "> l'intera AOI per tutta la stagione.",
        "",
    ]
    if metrics.truth_fires == 0:
        lines.insert(
            5,
            "> **Nessun perimetro EFFIS nella finestra.** Il servizio è "
            "pubblico e non richiede credenziali: se `fire_perimeters` è vuota "
            "va eseguito l'ingest. Le metriche sotto sono vuote per "
            "costruzione, non zero.",
        )
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


async def backtest_aoi(
    *,
    aoi_id: str,
    start: date,
    end: date,
    alert_level: RiskLevel,
    thresholds: WildfireThresholds,
    client: OpenMeteoHttpClient,
) -> WildfireBacktestMetrics:
    truth = await fetch_burnt_cells(aoi_id, start=start, end=end)
    if not truth:
        log.warning("backtest_wildfire.no_truth", aoi_id=aoi_id, start=str(start), end=str(end))
        metrics = WildfireBacktestMetrics(
            aoi_id=aoi_id,
            truth_fires=0,
            cells_warned=0,
            hits=0,
            false_alarms=0,
            misses=0,
            hit_rate=0.0,
            far=0.0,
            mean_lead_hours=0.0,
            base_rate=0.0,
            report_path=None,
        )
        path = write_report(metrics, start=start, end=end, alert_level=alert_level)
        return replace(metrics, report_path=path)

    bbox = await _aoi_bbox(aoi_id)
    if bbox is None:
        raise ValueError(f"AOI not found: {aoi_id!r}")

    # A month of spin-up before the window: the codes have to mean something
    # by the time the first fire is judged.
    spinup = timedelta(days=thresholds.fwi.spinup_days)
    days = [(start - spinup) + timedelta(days=i) for i in range((end - (start - spinup)).days + 1)]
    nodes = build_snapped_nodes(bbox, spacing=thresholds.fwi.node_spacing_deg)
    series = await client.get_fire_weather_grid(
        nodes=nodes,
        window_start=datetime.combine(days[0] - timedelta(days=1), time.min, UTC),
        window_end=datetime.combine(days[-1], time.max, UTC),
        use_archive=True,
    )
    chains = [
        replay_chain(
            snapshot=MeteoSnapshot(
                centroid_lon=lon,
                centroid_lat=lat,
                window_start=datetime.combine(days[0], time.min, UTC),
                window_end=datetime.combine(days[-1], time.max, UTC),
                samples=samples,
            ),
            days=days,
            thresholds=thresholds,
        )
        for (lon, lat), samples in zip(nodes, series, strict=True)
    ]

    static = await _static_by_cell(list(truth))
    metrics = evaluate(
        aoi_id=aoi_id,
        truth=truth,
        static=static,
        nodes=nodes,
        chains=chains,
        days=days,
        thresholds=thresholds,
        alert_level=alert_level,
        season=(start, end),
    )
    path = write_report(metrics, start=start, end=end, alert_level=alert_level)
    log.info(
        "backtest_wildfire.aoi.done",
        aoi_id=aoi_id,
        truth_fires=metrics.truth_fires,
        hit_rate=round(metrics.hit_rate, 4),
        far=round(metrics.far, 4),
        mean_lead_hours=round(metrics.mean_lead_hours, 1),
        base_rate=round(metrics.base_rate, 4),
        lift=round(_lift(metrics), 2),
        report=str(path),
    )
    return replace(metrics, report_path=path)


def _parse_date(name: str, default: date) -> date:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return date.fromisoformat(raw)
    except ValueError:
        log.warning("backtest_wildfire.bad_env", var=name, value=raw, using=str(default))
        return default


async def run() -> int:
    loaded = load_hazard_thresholds(HazardType.WILDFIRE)
    if not isinstance(loaded, WildfireThresholds):
        log.error("backtest_wildfire.bad_config", got=type(loaded).__name__)
        return 1

    today = datetime.now(UTC).date()
    end = _parse_date(_END_ENV, today - timedelta(days=1))
    start = _parse_date(_START_ENV, end - timedelta(days=400))
    level_raw = os.getenv(_LEVEL_ENV, RiskLevel.High.value)
    try:
        alert_level = RiskLevel(level_raw)
    except ValueError:
        log.warning("backtest_wildfire.bad_env", var=_LEVEL_ENV, value=level_raw, using="High")
        alert_level = RiskLevel.High

    client = OpenMeteoHttpClient()
    async with lifespan_pool():
        one = os.getenv(_AOI_ENV)
        aoi_ids = [one] if one else await list_aoi_ids()
        if not aoi_ids:
            log.warning("backtest_wildfire.no_aoi")
            return 0
        for aoi_id in aoi_ids:
            await backtest_aoi(
                aoi_id=aoi_id,
                start=start,
                end=end,
                alert_level=alert_level,
                thresholds=loaded,
                client=client,
            )
    await SharedHttpClient.aclose()
    return 0


__all__ = [
    "WildfireBacktestMetrics",
    "backtest_aoi",
    "evaluate",
    "fetch_burnt_cells",
    "replay_chain",
    "run",
    "write_report",
]
