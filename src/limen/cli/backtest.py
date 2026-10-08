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
from limen.data.db import acquire, lifespan_pool
from limen.data.migrate import run_migrations
from limen.data.repos.aoi_repo import get_aoi, list_aoi_ids
from limen.integrations._http import SharedHttpClient
from limen.integrations.openmeteo.client import OpenMeteoHttpClient
from limen.integrations.openmeteo.dtos import WeatherSample
from limen.integrations.openmeteo.grid import build_rain_nodes, nearest_node

log = get_logger(__name__)

#: Dove finisce il report. Configurabile con `LIMEN_REPORTS_DIR` perche'
#: dentro un container la directory di lavoro non e' scrivibile.
REPORTS_DIR = Path(os.getenv("LIMEN_REPORTS_DIR", "reports"))
# March 2009 Southern-Italy storm — 23 ITALICA events in Puglia/Basilicata
# cluster on the 7th, so the default window has a real truth set.
_DEFAULT_START = datetime(2009, 3, 4, 0, 0, tzinfo=UTC)
_DEFAULT_END = datetime(2009, 3, 10, 0, 0, tzinfo=UTC)

# Rainfall sampling grid step in degrees. Default 0.1° (~11 km) to exploit
# CERRA's 5.5 km resolution; ERA5 (~28 km) would warrant a coarser 0.25°.
_RAIN_NODE_DEG = 0.1
# Archive reanalysis for the antecedent rainfall. CERRA (5.5 km) resolves the
# localized triggering rain better than ERA5 (~28 km), but the self-hosted
# Open-Meteo instance (#142) does not serve it: it answers with every value
# null, which the parser reads as 0 mm. On 7 October 2026 that silently
# measured the landslide engine on a dry November 2019 in Liguria — the month
# of the 23-24 November floods. The default is the archive's own model;
# `LIMEN_BACKTEST_RAIN_MODEL=cerra` stays available where CERRA is served.
_DEFAULT_RAIN_MODEL = ""
# Warning horizon: an alert this many hours (or fewer) before the event counts
# as a hit. Generous by design — antecedent-driven landslides warn days ahead.
_DEFAULT_LEAD_MAX_HOURS = 120.0
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
    """Return ``{cell_id: first_event_time}`` from the dated landslide-event
    catalogue (ITALICA / e-ITALICA) for events in ``[start, end]`` inside
    ``aoi_id``. Times are UTC; the earliest event per cell is the anchor."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT g.id AS cell_id, MIN(e.event_time) AS first_event
            FROM landslide_events e
            JOIN grid_cells g
              ON ST_Intersects(g.geom, e.geom)
            WHERE g.aoi_id = $1
              AND e.event_time >= $2
              AND e.event_time <= $3
            GROUP BY g.id
            """,
            aoi_id,
            start,
            end,
        )
    return {str(r["cell_id"]): r["first_event"] for r in rows}


async def _fetch_static_factors(aoi_id: str) -> list[tuple[StaticFactors, float, float]]:
    """Return ``(static_factors, centroid_lon, centroid_lat)`` per cell.

    The centroid lets the backtest assign each cell the rainfall of its
    nearest sampling node rather than a single AOI-wide series.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT c.cell_id, c.iffi_density_500, c.slope_deg, c.pai_class_norm,
                   c.litho_weight, c.s_static,
                   ST_X(ST_Centroid(g.geom)) AS lon, ST_Y(ST_Centroid(g.geom)) AS lat
            FROM cell_static_factors c
            JOIN grid_cells g ON g.id = c.cell_id
            WHERE g.aoi_id = $1
            """,
            aoi_id,
        )
    out: list[tuple[StaticFactors, float, float]] = []
    for r in rows:
        sf = StaticFactors(
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
        out.append((sf, float(r["lon"]), float(r["lat"])))
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


@dataclass(frozen=True, slots=True)
class Antecedenti:
    """Pioggia dei giorni prima e umidità del suolo, da una serie oraria.

    Le stesse due grandezze che lo sweep operativo passa al motore
    (`MeteoFetchExecutor`): la somma della pioggia giornaliera sugli ultimi
    ``api_days`` giorni fino al giorno di valutazione compreso, e la media
    dell'umidità 0-7 cm sulle ``soil_hours`` ore prima. Senza, il backtest le
    lasciava al valore neutro 0,5 — il 55 % della componente pioggia fermo
    proprio dove la produzione lo muove (#122).
    """

    pioggia_giorno: dict[date, float]
    umidita: list[tuple[datetime, float]]
    api_days: int = 30
    soil_hours: int = 48

    @classmethod
    def da_serie(cls, campioni: list[WeatherSample], **kw: int) -> Antecedenti:
        giorni: dict[date, float] = {}
        for c in campioni:
            giorni[c.timestamp.date()] = giorni.get(c.timestamp.date(), 0.0) + c.precipitation_mm
        umidita = sorted(
            (c.timestamp, c.soil_moisture_0_7_cm)
            for c in campioni
            if c.soil_moisture_0_7_cm is not None
        )
        return cls(pioggia_giorno=giorni, umidita=umidita, **kw)

    def api(self, t: datetime) -> float | None:
        giorni = [t.date() - timedelta(days=d) for d in range(self.api_days)]
        if not any(g in self.pioggia_giorno for g in giorni):
            return None
        return sum(self.pioggia_giorno.get(g, 0.0) for g in giorni)

    def suolo(self, t: datetime) -> float | None:
        da = t - timedelta(hours=self.soil_hours)
        valori = [v for ts, v in self.umidita if da <= ts <= t]
        return sum(valori) / len(valori) if valori else None


def _match_truth(
    alert_times: dict[str, list[datetime]],
    truth: dict[str, datetime],
    *,
    lead_max_hours: float,
) -> tuple[int, int, list[float]]:
    """Hit, mancate e preavvisi, confrontando allerte ed eventi.

    Un hit e' **un'allerta qualunque** nelle ore che precedono l'evento, non
    la prima allerta della finestra. La versione precedente guardava solo la
    piu' antica: con una soglia permissiva quasi ogni cella si accende il
    primo giorno, e una cella che al momento della frana era in allerta da
    giorni risultava *mancata* perche' il suo primo allarme cadeva fuori
    dall'orizzonte. Misurato in Liguria a `Moderate`: il 72% delle ore-cella
    era in allerta e il backtest dichiarava 118 mancate su 131.

    Il preavviso riportato e' quello dell'allerta piu' precoce **ancora dentro
    l'orizzonte**: il tempo che un operatore ha avuto davvero.
    """
    hits = 0
    misses = 0
    leads: list[float] = []
    for cell_id, event_time in truth.items():
        dentro = [
            t
            for t in alert_times.get(cell_id, ())
            if 0 < (event_time - t).total_seconds() / 3600.0 <= lead_max_hours
        ]
        if not dentro:
            misses += 1
            continue
        hits += 1
        leads.append((event_time - min(dentro)).total_seconds() / 3600.0)
    return hits, misses, leads


def _evaluate(
    *,
    aoi_id: str,
    cells: list[tuple[StaticFactors, float, float]],
    nodes: list[tuple[float, float]],
    node_rainfall: list[list[RainfallSample]],
    truth: dict[str, datetime],
    start: datetime,
    end: datetime,
    alert_level: RiskLevel,
    lead_max_hours: float,
    antecedenti: list[Antecedenti | None] | None = None,
) -> _BacktestMetrics:
    """``antecedenti`` è allineato ai nodi (modalità `nodo`) o lungo 1 (modalità
    `regione`, un valore per tutta l'area come in produzione); ``None`` lascia
    pioggia antecedente e umidità al valore neutro, come prima."""
    thresholds = load_regional_thresholds()
    engine = MultiFactorScoringEngine(thresholds)
    hours = _hourly_window(start, end)

    # Assign each cell to its nearest rainfall node once.
    cell_node = [nearest_node(lon, lat, nodes) for _, lon, lat in cells]

    # Gli istanti di allerta delle sole celle di verita': per decidere un hit
    # serve sapere se la cella era in allerta **nelle ore prima dell'evento**,
    # non se lo era stata una volta a inizio finestra.
    alert_times: dict[str, list[datetime]] = {cell_id: [] for cell_id in truth}
    alerted_cells: set[str] = set()
    alerts_total = 0
    for t in hours:
        # Slice each node's antecedent series once, then reuse across the
        # (many) cells that map to that node.
        node_slice = [
            _synthesise_rainfall(samples=node_rainfall[n], as_of=t) for n in range(len(nodes))
        ]
        stato = [
            (a.api(t), a.suolo(t)) if a is not None else (None, None) for a in antecedenti or []
        ]
        for i, (sf, _lon, _lat) in enumerate(cells):
            api_mm, suolo = (
                stato[cell_node[i] if len(stato) == len(nodes) else 0] if stato else (None, None)
            )
            bundle = CellFeatureBundle(
                aoi_id=aoi_id,
                cell_id=sf.cell_id,
                static=sf,
                dynamic=DynamicInputs(
                    valuation_time=t,
                    rainfall=node_slice[cell_node[i]],
                    api_30_mm=api_mm,
                    soil_moisture_0_7=suolo,
                ),
            )
            scored = engine.score(bundle)
            if _level_at_least(scored.level, alert_level):
                alerts_total += 1
                alerted_cells.add(sf.cell_id)
                if sf.cell_id in alert_times:
                    alert_times[sf.cell_id].append(t)

    hits, misses, leads = _match_truth(alert_times, truth, lead_max_hours=lead_max_hours)

    false_alarms = max(0, len(alerted_cells) - hits)
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
# Open-Meteo historical fetch (one ERA5 series per sampling node)
# ---------------------------------------------------------------------------
async def _antecedenti_regione(
    aoi_id: str, bbox: tuple[float, ...], start: datetime, end: datetime
) -> Antecedenti | None:
    """Gli antecedenti al centro dell'area, come li legge lo sweep operativo."""
    snapshot = await OpenMeteoHttpClient().get_meteo_snapshot(
        aoi_id=aoi_id,
        bbox=(bbox[0], bbox[1], bbox[2], bbox[3]),
        window_start=start - timedelta(days=31),
        window_end=end,
        use_archive=True,
    )
    return Antecedenti.da_serie(list(snapshot.samples)) if snapshot is not None else None


def rain_was_measured(node_rainfall: list[list[RainfallSample]]) -> bool:
    """False when no node received a single drop over the whole window.

    The archive answers an unavailable model with nulls, and the parser reads
    a null as 0 mm: indistinguishable, per sample, from a dry hour. Over a
    whole region and a whole window, though, all-zero is not a climate.
    """
    return any(s.precipitation_mm > 0 for series in node_rainfall for s in series)


async def _fetch_rainfall_grid(
    *,
    nodes: list[tuple[float, float]],
    start: datetime,
    end: datetime,
    model: str | None = None,
) -> list[list[RainfallSample]]:
    """One antecedent-inclusive precipitation series per sampling node."""
    client = OpenMeteoHttpClient()
    grid = await client.get_rainfall_grid(
        nodes=nodes,
        window_start=start - timedelta(hours=48),
        window_end=end,
        model=model,
    )
    if len(grid) != len(nodes):
        # Guard against batch misalignment: pad/truncate to the node count.
        log.warning("backtest.rainfall.node_count", expected=len(nodes), got=len(grid))
        grid = (grid + [[] for _ in nodes])[: len(nodes)]
    return [
        [RainfallSample(timestamp=s.timestamp, precipitation_mm=s.precipitation_mm) for s in series]
        for series in grid
    ]


# ---------------------------------------------------------------------------
# CLI runner
# ---------------------------------------------------------------------------
def _parse_dt(env_name: str, default: datetime) -> datetime:
    raw = os.getenv(env_name)
    if not raw:
        return default
    parsed = datetime.fromisoformat(raw)
    # Una data scritta a mano (`2019-11-01`) non porta il fuso, e piu' avanti
    # finisce a confronto con i campioni di pioggia, che ce l'hanno: senza
    # questa riga il comando muore a meta' con "can't compare offset-naive and
    # offset-aware datetimes". Il default e' gia' in UTC, quindi il difetto si
    # vedeva solo passando la finestra da variabile d'ambiente.
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


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
    rain_model = os.getenv("LIMEN_BACKTEST_RAIN_MODEL", _DEFAULT_RAIN_MODEL).strip() or None
    node_deg = float(os.getenv("LIMEN_BACKTEST_RAIN_NODE_DEG", str(_RAIN_NODE_DEG)))
    lead_max = float(os.getenv("LIMEN_BACKTEST_LEAD_MAX_HOURS", str(_DEFAULT_LEAD_MAX_HOURS)))
    # Come la produzione (`regione`), per nodo (la variante da misurare), o al
    # valore neutro di prima (`neutro`).
    modo = os.getenv("LIMEN_BACKTEST_ANTECEDENT", "regione").strip() or "regione"
    if modo not in ("regione", "nodo", "neutro"):
        log.error("backtest.bad_antecedent", value=modo)
        return 1

    try:
        async with lifespan_pool():
            await run_migrations()
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
                nodes = build_rain_nodes(bbox, spacing=node_deg)
                antecedenti: list[Antecedenti | None] | None = None
                if modo == "neutro":
                    node_rainfall = await _fetch_rainfall_grid(
                        nodes=nodes, start=start, end=end, model=rain_model
                    )
                else:
                    # Trenta giorni prima della finestra: la pioggia antecedente
                    # del primo istante deve già esistere.
                    grezzo = await OpenMeteoHttpClient().get_rainfall_grid(
                        nodes=nodes,
                        window_start=start - timedelta(days=31),
                        window_end=end,
                        model=rain_model,
                        with_soil=True,
                    )
                    node_rainfall = [
                        [
                            RainfallSample(
                                timestamp=c.timestamp, precipitation_mm=c.precipitation_mm
                            )
                            for c in serie
                        ]
                        for serie in grezzo
                    ]
                    if modo == "nodo":
                        antecedenti = [Antecedenti.da_serie(serie) for serie in grezzo]
                    else:
                        antecedenti = [await _antecedenti_regione(aoi_id, bbox, start, end)]
                if not rain_was_measured(node_rainfall):
                    # Zero millimetres on every node for the whole window is
                    # not weather, it is a model the archive does not serve.
                    # Scoring on it measures the static half of the engine
                    # and reports it as the whole.
                    log.error(
                        "backtest.rainfall.empty",
                        aoi_id=aoi_id,
                        rain_model=rain_model or "default",
                        nodes=len(nodes),
                    )
                    return 1
                log.info(
                    "backtest.aoi.loaded",
                    aoi_id=aoi_id,
                    cells=len(cells),
                    truth_events=len(truth),
                    rain_model=rain_model or "era5",
                    antecedent=modo,
                    rain_nodes=len(nodes),
                    rain_samples=sum(len(s) for s in node_rainfall),
                )

                metrics = _evaluate(
                    aoi_id=aoi_id,
                    cells=cells,
                    nodes=nodes,
                    node_rainfall=node_rainfall,
                    truth=truth,
                    start=start,
                    end=end,
                    alert_level=alert_level,
                    lead_max_hours=lead_max,
                    antecedenti=antecedenti,
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
    return 0


def main() -> int:
    import asyncio

    return asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
