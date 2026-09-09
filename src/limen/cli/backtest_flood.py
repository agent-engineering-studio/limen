"""``limen backtest-flood`` — rigioca i perimetri allagati Copernicus EMS (#64).

La domanda §2.5 posta all'alluvione: **nelle 72 h prima che l'acqua arrivasse,
quella cella era già in classe alta?** Hit, falsi allarmi, preavviso e — come
impone il progetto — il **tasso di base** accanto all'hit rate, perché un
modello che dichiara pericolo ogni giorno di novembre massimizza l'hit rate
senza discriminare niente.

**Due repliche, non una.** Il trigger pluviale è *previsionale*: guarda la
pioggia dei prossimi 72 h. Rigiocarlo con la pioggia poi osservata misurerebbe
il motore con una previsione perfetta e si prenderebbe un merito che il
sistema operativo non ha. Misurato a Faenza sul 17-19 settembre 2024: 208,7 mm
osservati, 157,1 previsti un giorno prima, 101,3 tre giorni prima — con la
soglia a 80 mm/72 h è la differenza fra un allarme e un silenzio. Quindi:

* ``issued``   — la previsione **come fu emessa** (`precipitation_previous_dayN`
  dell'archivio Open-Meteo): la skill operativa, quello che Limen avrebbe
  detto.
* ``observed``  — la pioggia poi caduta: il **tetto** raggiungibile con una
  previsione perfetta. Serve a sapere dove investire, sulle soglie o sul dato
  in ingresso.

L'archivio delle previsioni emesse parte da inizio febbraio 2024. Per gli
eventi precedenti (fra cui l'Emilia-Romagna di maggio 2023, il truth set più
grande) solo il tetto è misurabile, e il report lo dice invece di far passare
il tetto per skill.

Passo **giornaliero** e non orario: la finestra pluviale è 72 h e GloFAS è un
dato giornaliero, quindi rivalutare ogni ora costerebbe 24 volte tanto senza
aggiungere risoluzione.

Env:

* ``LIMEN_BACKTEST_FLOOD_AOI``    — una AOI; assente ⇒ tutte quelle con eventi.
* ``LIMEN_BACKTEST_FLOOD_START`` / ``_END`` — ISO; assenti ⇒ finestra dedotta
  dagli eventi dell'AOI.
* ``LIMEN_BACKTEST_FLOOD_LEVEL``  — livello che conta come allerta (default ``High``).
* ``LIMEN_BACKTEST_FLOOD_MODE``   — ``issued`` | ``observed`` | ``both`` (default).
* ``LIMEN_BACKTEST_FLOOD_NODE_DEG`` — passo del reticolo meteo (default 0.1°).
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Literal

from limen.core.logging import get_logger
from limen.core.models.hazard import HazardType
from limen.core.models.risk import (
    CellFeatureBundle,
    DynamicInputs,
    RiskLevel,
    StaticFactors,
)
from limen.core.scoring.flood.engine import FloodScoringEngine
from limen.core.scoring.flood.trigger import fluvial_trigger
from limen.core.scoring.regional_thresholds import (
    FloodThresholds,
    load_hazard_thresholds,
)
from limen.data.db import acquire, lifespan_pool
from limen.data.migrate import run_migrations
from limen.data.repos import flood_events_repo
from limen.data.repos.flood_events_repo import ActivationSummary
from limen.integrations._http import SharedHttpClient
from limen.integrations.copernicus_ems.client import catalogue_provenance

log = get_logger(__name__)

REPORTS_DIR = Path("reports")

_AOI_ENV = "LIMEN_BACKTEST_FLOOD_AOI"
_START_ENV = "LIMEN_BACKTEST_FLOOD_START"
_END_ENV = "LIMEN_BACKTEST_FLOOD_END"
_LEVEL_ENV = "LIMEN_BACKTEST_FLOOD_LEVEL"
_MODE_ENV = "LIMEN_BACKTEST_FLOOD_MODE"
_NODE_ENV = "LIMEN_BACKTEST_FLOOD_NODE_DEG"

#: Passo del reticolo meteo. 0.1° (~11 km) come il resto della pipeline flood.
_DEFAULT_NODE_DEG = 0.1

#: Giorni di coda prima del primo evento, per avere allerte da misurare e
#: giornate tranquille in cui contare i falsi allarmi.
_PAD_BEFORE_DAYS = 14
_PAD_AFTER_DAYS = 3

#: Inizio dell'archivio delle previsioni emesse di Open-Meteo (misurato: le
#: variabili `previous_dayN` sono vuote a metà gennaio 2024 e piene dal 1°
#: febbraio). Prima di questa data la modalità `issued` non è misurabile.
ISSUED_ARCHIVE_START = date(2024, 2, 1)

Mode = Literal["issued", "observed"]

_LEVEL_ORDER = (
    RiskLevel.None_,
    RiskLevel.Low,
    RiskLevel.Moderate,
    RiskLevel.High,
    RiskLevel.VeryHigh,
)


def _at_least(level: RiskLevel, threshold: RiskLevel) -> bool:
    return _LEVEL_ORDER.index(level) >= _LEVEL_ORDER.index(threshold)


@dataclass(frozen=True, slots=True)
class FloodBacktestMetrics:
    aoi_id: str
    mode: Mode
    truth_cells: int
    days: int
    cells_scored: int
    hits: int
    misses: int
    #: Sequenze contigue di allerta. Descrittivo: quanti avvisi distinti.
    alert_episodes: int
    #: Cella-giorno di allerta seguita dall'evento entro l'orizzonte.
    true_days: int
    #: Cella-giorno di allerta su area osservata e trovata asciutta.
    false_days: int
    #: Cella-giorno che nessun passaggio satellitare ha coperto entro
    #: l'orizzonte. Non sono falsi: sono senza risposta, e contarli fra i
    #: falsi è ciò che produsse un FAR del 100% al primo giro.
    unverifiable_days: int
    hit_rate: float
    far: float
    mean_lead_hours: float
    #: Quota di giornate in cui una cella poi allagata era in allerta comunque.
    #: È il metro dell'hit rate: senza, un modello che grida al lupo ogni
    #: giorno di piena passerebbe per bravo.
    base_rate: float
    #: Giorni-cella di allerta per ramo dominante.
    pluvial_driven: int
    fluvial_driven: int
    measurable: bool
    #: Inizio effettivo della replica: `issued` parte dall'archivio delle
    #: previsioni emesse, che comincia dopo la finestra degli eventi.
    window_start: date | None


def _unmeasurable(aoi_id: str, mode: Mode, *, days: int) -> FloodBacktestMetrics:
    """Replica non misurabile: dato assente, non modello sbagliato."""
    return FloodBacktestMetrics(
        aoi_id=aoi_id,
        mode=mode,
        truth_cells=0,
        days=days,
        cells_scored=0,
        hits=0,
        misses=0,
        alert_episodes=0,
        true_days=0,
        false_days=0,
        unverifiable_days=0,
        hit_rate=0.0,
        far=0.0,
        mean_lead_hours=0.0,
        base_rate=0.0,
        pluvial_driven=0,
        fluvial_driven=0,
        measurable=False,
        window_start=None,
    )


@dataclass(frozen=True, slots=True)
class _Cell:
    static: StaticFactors
    node: int


# ---------------------------------------------------------------------------
# Letture dal database
# ---------------------------------------------------------------------------
async def _fetch_cells(
    aoi_id: str, *, floor: float, keep: set[str] | None = None
) -> list[tuple[StaticFactors, float, float]]:
    """Celle con la suscettibilità che il motore userebbe, e il centroide.

    Due filtri, entrambi **esatti** e non approssimazioni.

    Le celle sotto ``susceptibility.floor`` sono escluse alla fonte: il motore
    le manda a zero qualunque pioggia faccia, quindi tenerle vorrebbe dire
    valutare per giorni delle celle il cui esito è già noto. Una cella non
    mappata **resta** dentro con `unmapped`: "non studiato" non è "non
    allagabile", ed è una scelta del motore che il backtest deve rispettare.

    ``keep`` restringe alle celle che possono entrare in una metrica: quelle
    allagate e quelle dentro una maschera di osservazione. Una cella che non è
    né l'una né l'altra non può essere un hit (non è verità) né un falso
    allarme (nessuno ha guardato): produce solo giorni `non verificabili`, che
    sono già fuori da tutti i denominatori. Escluderle non cambia un numero e
    porta il Piemonte da 26.140 celle a 84 — cioè da una richiesta che
    Open-Meteo rifiuta con 429 a una che serve.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT c.cell_id, c.flood_hazard_norm, c.imperviousness_norm,
                   ST_X(ST_Centroid(g.geom)) AS lon,
                   ST_Y(ST_Centroid(g.geom)) AS lat
            FROM cell_static_factors c
            JOIN grid_cells g ON g.id = c.cell_id
            WHERE g.aoi_id = $1
              AND (c.flood_hazard_norm IS NULL OR c.flood_hazard_norm >= $2)
              AND ($3::text[] IS NULL OR c.cell_id = ANY($3::text[]))
            """,
            aoi_id,
            floor,
            None if keep is None else sorted(keep),
        )
    out: list[tuple[StaticFactors, float, float]] = []
    for r in rows:
        static = StaticFactors(
            cell_id=str(r["cell_id"]),
            flood_hazard_norm=(
                float(r["flood_hazard_norm"]) if r["flood_hazard_norm"] is not None else None
            ),
            imperviousness_norm=(
                float(r["imperviousness_norm"]) if r["imperviousness_norm"] is not None else None
            ),
        )
        out.append((static, float(r["lon"]), float(r["lat"])))
    return out


async def _aois_with_events() -> list[str]:
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT g.aoi_id
            FROM flood_events e
            JOIN grid_cells g ON ST_Intersects(g.geom, e.geom)
            ORDER BY 1
            """
        )
    return [str(r["aoi_id"]) for r in rows]


async def _event_windows(aoi_id: str) -> list[tuple[datetime, datetime]]:
    """Una finestra per evento, sovrapposizioni unite.

    Non una finestra continua dal primo all'ultimo evento. Sull'Emilia-Romagna
    sarebbero 554 giorni contro i 51 che contengono davvero qualcosa, e
    Open-Meteo risponde 429 alla richiesta che ne consegue.

    Non si perde niente di misurabile: un giorno di allerta entra nel FAR solo
    se un passaggio satellitare lo copre entro l'orizzonte, e i passaggi ci
    sono soltanto attorno agli eventi. La finestra continua comprerebbe mesi
    di giornate `non verificabili`, che sono già escluse dal denominatore.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT e.event_time
            FROM flood_events e
            JOIN grid_cells g ON ST_Intersects(g.geom, e.geom)
            WHERE g.aoi_id = $1
            ORDER BY 1
            """,
            aoi_id,
        )
    spans = [
        (
            r["event_time"] - timedelta(days=_PAD_BEFORE_DAYS),
            r["event_time"] + timedelta(days=_PAD_AFTER_DAYS),
        )
        for r in rows
    ]
    merged: list[tuple[datetime, datetime]] = []
    for lo, hi in spans:
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return merged


# ---------------------------------------------------------------------------
# Meteo storico
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class _NodeSeries:
    """Serie per nodo, già ridotte a un valore per giorno."""

    #: Accumulo 72 h dal giorno d, come previsto **il giorno d**.
    rain_issued: dict[date, float]
    #: Accumulo 72 h dal giorno d, come poi osservato.
    rain_observed: dict[date, float]
    #: Umidità del suolo 0-7 cm a mezzanotte del giorno d.
    soil: dict[date, float]
    #: Rapporto portata: picco dei 7 giorni seguenti / media dei 31 precedenti.
    discharge_ratio: dict[date, float]


def _daily_sums(stamps: Sequence[str], values: Sequence[float | None]) -> dict[date, float]:
    out: dict[date, float] = {}
    for stamp, value in zip(stamps, values, strict=False):
        if value is None:
            continue
        day = datetime.fromisoformat(str(stamp)).date()
        out[day] = out.get(day, 0.0) + float(value)
    return out


def _midnight_values(stamps: Sequence[str], values: Sequence[float | None]) -> dict[date, float]:
    out: dict[date, float] = {}
    for stamp, value in zip(stamps, values, strict=False):
        if value is None:
            continue
        when = datetime.fromisoformat(str(stamp))
        if when.hour == 0:
            out[when.date()] = float(value)
    return out


def _accumulate_72h(
    day0: dict[date, float], day1: dict[date, float], day2: dict[date, float]
) -> dict[date, float]:
    """Somma dei tre giorni, ognuno preso dalla previsione emessa il primo.

    ``precipitation_previous_dayN`` dà, per un'ora, la previsione di N giorni
    prima. Quindi l'accumulo 72 h *come emesso il giorno d* è: il giorno d
    dalla corsa di d, il giorno d+1 dalla corsa di d (= `previous_day1` letto
    su d+1), il giorno d+2 dalla corsa di d (= `previous_day2` letto su d+2).
    Ricomporlo così è ciò che distingue una previsione da un consuntivo.
    """
    out: dict[date, float] = {}
    for day in day0:
        first = day0.get(day)
        second = day1.get(day + timedelta(days=1))
        third = day2.get(day + timedelta(days=2))
        if first is None or second is None or third is None:
            continue
        out[day] = first + second + third
    return out


def _accumulate_observed(daily: dict[date, float]) -> dict[date, float]:
    out: dict[date, float] = {}
    for day in daily:
        parts = [daily.get(day + timedelta(days=k)) for k in (0, 1, 2)]
        if any(p is None for p in parts):
            continue
        out[day] = sum(p for p in parts if p is not None)
    return out


def _discharge_ratios(daily: dict[date, float]) -> dict[date, float]:
    """Rapporto per giorno: picco dei 7 giorni dopo / media dei 31 prima.

    La stessa definizione dell'operativo (`_fluvial` in openmeteo/flood.py),
    che lì usa ``past_days``/``forecast_days`` perché guarda "adesso"; qui la
    finestra va fatta scorrere a mano, altrimenti il replay chiederebbe a
    GloFAS lo stato di oggi per un giorno del 2024.
    """
    out: dict[date, float] = {}
    for day in daily:
        past = [
            daily[day - timedelta(days=k)] for k in range(1, 32) if day - timedelta(days=k) in daily
        ]
        future = [
            daily[day + timedelta(days=k)] for k in range(0, 7) if day + timedelta(days=k) in daily
        ]
        if len(past) < 15 or not future:
            continue
        baseline = sum(past) / len(past)
        if baseline <= 0.0:
            continue
        out[day] = max(future) / baseline
    return out


#: Frazione del deflusso di base massimo dell'AOI sotto la quale un nodo non
#: conta come corso d'acqua. Lo stesso `min_baseline_fraction` dell'operativo:
#: il rapporto è patologico sui rigagnoli (misurato 62,0 su un fosso dove i
#: fiumi veri stavano a 1,25), e un backtest che non applica il filtro misura
#: un FAR che il sistema reale non produce.
_MIN_BASELINE_FRACTION = 0.1


def _trickle_floor(discharges: Sequence[dict[date, float]]) -> float:
    """Soglia di deflusso di base sotto cui un nodo è un fosso, non un fiume."""
    means = [sum(series.values()) / len(series) for series in discharges if series]
    return max(means) * _MIN_BASELINE_FRACTION if means else 0.0


async def _fetch_node_series(
    nodes: list[tuple[float, float]], *, start: date, end: date
) -> list[_NodeSeries]:
    """Una serie per nodo: previsioni emesse, osservato, suolo, portata."""
    from limen.integrations.openmeteo.flood import FLOOD_URL, OpenMeteoFloodClient

    client = OpenMeteoFloodClient()
    # +3 giorni: l'accumulo a 72 h del penultimo giorno guarda oltre la fine.
    fetch_end = end + timedelta(days=3)
    hist = await client.fetch_grid(
        "https://historical-forecast-api.open-meteo.com/v1/forecast",
        nodes,
        {
            "hourly": (
                "precipitation,precipitation_previous_day1,"
                "precipitation_previous_day2,soil_moisture_0_to_7cm"
            ),
            "start_date": start.isoformat(),
            "end_date": fetch_end.isoformat(),
            "timezone": "UTC",
        },
        "backtest_flood.history",
    )
    flow = await client.fetch_grid(
        FLOOD_URL,
        nodes,
        {
            "daily": "river_discharge",
            "start_date": (start - timedelta(days=32)).isoformat(),
            "end_date": fetch_end.isoformat(),
            "timezone": "UTC",
        },
        "backtest_flood.discharge",
    )

    discharges: list[dict[date, float]] = []
    for index in range(len(nodes)):
        river = flow[index] if index < len(flow) else {}
        river_daily = river.get("daily") or {}
        series: dict[date, float] = {}
        for stamp, value in zip(
            river_daily.get("time") or [], river_daily.get("river_discharge") or [], strict=False
        ):
            if value is None:
                continue
            series[date.fromisoformat(str(stamp))] = float(value)
        discharges.append(series)
    # Il filtro è relativo al massimo dell'AOI, quindi va deciso dopo aver
    # letto tutti i nodi: per questo la portata si raccoglie in un giro a sé.
    floor = _trickle_floor(discharges)
    dropped = 0

    out: list[_NodeSeries] = []
    for index in range(len(nodes)):
        point = hist[index] if index < len(hist) else {}
        hourly = point.get("hourly") or {}
        stamps = hourly.get("time") or []
        day0 = _daily_sums(stamps, hourly.get("precipitation") or [])
        day1 = _daily_sums(stamps, hourly.get("precipitation_previous_day1") or [])
        day2 = _daily_sums(stamps, hourly.get("precipitation_previous_day2") or [])
        soil = _midnight_values(stamps, hourly.get("soil_moisture_0_to_7cm") or [])

        discharge = discharges[index]
        mean_flow = sum(discharge.values()) / len(discharge) if discharge else 0.0
        if mean_flow < floor:
            # Nessun corso d'acqua qui: `None`, che il trigger legge come
            # assenza di segnale e non come fiume in secca.
            ratios: dict[date, float] = {}
            dropped += 1
        else:
            ratios = _discharge_ratios(discharge)

        out.append(
            _NodeSeries(
                rain_issued=_accumulate_72h(day0, day1, day2),
                rain_observed=_accumulate_observed(day0),
                soil=soil,
                discharge_ratio=ratios,
            )
        )
    log.info(
        "backtest_flood.nodes",
        nodes=len(nodes),
        without_river=dropped,
        trickle_floor=round(floor, 3),
    )
    return out


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------
def _days(start: datetime, end: datetime) -> list[date]:
    out: list[date] = []
    day = start.date()
    while day <= end.date():
        out.append(day)
        day += timedelta(days=1)
    return out


def _node_key(lon: float, lat: float, *, spacing: float) -> tuple[int, int]:
    """Indice del punto di reticolo **globale** più vicino.

    Sostituisce una scansione ``nearest_node`` su tutti i nodi del bbox: su
    Emilia-Romagna erano 23.214 celle per 675 nodi, 15,7 milioni di confronti
    per un risultato che l'aritmetica dà esatto. E soprattutto i nodi nascono
    dalle celle e non dal rettangolo: il bbox dell'Emilia-Romagna arriva a
    9,1° E, che è Lombardia, e chiedere quei punti a Open-Meteo era metà del
    peso della richiesta che tornava 429.

    Resta il reticolo globale di :func:`build_snapped_nodes`, quindi
    l'identità di un nodo dipende dal passo e non dai confini dell'AOI.
    """
    return (round(lon / spacing), round(lat / spacing))


def _nodes_from_cells(
    cells: Sequence[tuple[StaticFactors, float, float]], *, spacing: float
) -> tuple[list[tuple[float, float]], list[int]]:
    """``(nodi, indice del nodo per cella)`` dalle celle effettivamente presenti."""
    index_by_key: dict[tuple[int, int], int] = {}
    nodes: list[tuple[float, float]] = []
    per_cell: list[int] = []
    for _, lon, lat in cells:
        key = _node_key(lon, lat, spacing=spacing)
        position = index_by_key.get(key)
        if position is None:
            position = len(nodes)
            index_by_key[key] = position
            nodes.append((key[0] * spacing, key[1] * spacing))
        per_cell.append(position)
    return nodes, per_cell


@dataclass(slots=True)
class _Tally:
    """Tallies grezzi, sommabili fra finestre. Le percentuali si fanno alla fine."""

    #: Giorni di allerta per cella, uniti su tutte le finestre.
    alert_days: dict[str, list[date]]
    #: Celle di verità incontrate, con il primo evento.
    truth: dict[str, datetime]
    truth_cell_days: int
    truth_alert_days: int
    days: int
    measurable: bool
    #: Quale ramo ha portato l'allerta. Serve per ritarare con una prova
    #: invece che a intuito: un FAR alto per colpa del rapporto di portata si
    #: corregge sul ramo fluviale, e toccare la soglia pluviale non lo
    #: sposterebbe di un punto.
    pluvial_driven: int = 0
    fluvial_driven: int = 0

    @classmethod
    def empty(cls) -> _Tally:
        return cls({}, {}, 0, 0, 0, False)

    def merge(self, other: _Tally) -> None:
        for cell_id, days in other.alert_days.items():
            self.alert_days.setdefault(cell_id, []).extend(days)
        self.truth.update(other.truth)
        self.truth_cell_days += other.truth_cell_days
        self.truth_alert_days += other.truth_alert_days
        self.days += other.days
        self.measurable = self.measurable or other.measurable
        self.pluvial_driven += other.pluvial_driven
        self.fluvial_driven += other.fluvial_driven


def _replay(
    *,
    aoi_id: str,
    mode: Mode,
    cells: Sequence[tuple[StaticFactors, float, float]],
    cell_node: Sequence[int],
    series: Sequence[_NodeSeries],
    truth: dict[str, datetime],
    start: datetime,
    end: datetime,
    alert_level: RiskLevel,
    thresholds: FloodThresholds,
    engine: FloodScoringEngine,
) -> _Tally:
    """Rigioca una finestra e restituisce i tallies."""
    tally = _Tally.empty()
    tally.truth = dict(truth)

    for day in _days(start, end):
        tally.days += 1
        # Pre-filtro esatto, non un'euristica: il punteggio è
        # `suscettibilita * max(pluviale, fluviale)`, e `pluvial_trigger`
        # restituisce 0 sotto `threshold_mm` a prescindere da suolo e
        # impermeabilizzazione. Se entrambi i segnali sono sotto soglia su un
        # nodo, ogni cella di quel nodo vale zero: valutarle sarebbe lavoro
        # per un esito già noto.
        active: dict[int, tuple[float | None, float | None, float]] = {}
        for index, node in enumerate(series):
            rain = (node.rain_issued if mode == "issued" else node.rain_observed).get(day)
            ratio = node.discharge_ratio.get(day)
            if rain is not None:
                tally.measurable = True
            rain_hot = rain is not None and rain > thresholds.pluvial.threshold_mm
            flow_hot = fluvial_trigger(ratio, fluvial=thresholds.fluvial) > 0.0
            if rain_hot or flow_hot:
                active[index] = (rain, ratio, node.soil.get(day, float("nan")))

        moment = datetime.combine(day, time(0, 0), tzinfo=UTC)
        for position, (static, _lon, _lat) in enumerate(cells):
            is_truth = static.cell_id in truth
            if is_truth:
                tally.truth_cell_days += 1
            hot = active.get(cell_node[position])
            if hot is None:
                continue
            rain, ratio, soil = hot
            bundle = CellFeatureBundle(
                aoi_id=aoi_id,
                cell_id=static.cell_id,
                static=static,
                dynamic=DynamicInputs(
                    valuation_time=moment,
                    flood_forecast_rain_72h_mm=rain,
                    river_discharge_ratio=ratio,
                    # NaN è il segnaposto di "il nodo non ha umidità per quel
                    # giorno": il trigger tratta None come a metà fra asciutto
                    # e saturo, che è la scelta giusta e documentata.
                    soil_moisture_0_7=None if soil != soil else soil,
                ),
            )
            scored = engine.score(bundle)
            if not _at_least(scored.level, alert_level):
                continue
            tally.alert_days.setdefault(static.cell_id, []).append(day)
            if scored.breakdown.pluvial >= scored.breakdown.fluvial:
                tally.pluvial_driven += 1
            else:
                tally.fluvial_driven += 1
            if is_truth:
                tally.truth_alert_days += 1
    return tally


def _metrics(
    *,
    aoi_id: str,
    mode: Mode,
    tally: _Tally,
    observed: dict[str, list[datetime]],
    cells_scored: int,
    window_start: date | None,
    thresholds: FloodThresholds,
) -> FloodBacktestMetrics:
    lead_max_hours = float(thresholds.pluvial.window_hours)

    # Hit: la prima allerta dentro l'orizzonte di preavviso prima dell'evento.
    hits = 0
    leads: list[float] = []
    for cell_id, event_time in tally.truth.items():
        earliest: datetime | None = None
        for day in tally.alert_days.get(cell_id, []):
            moment = datetime.combine(day, time(0, 0), tzinfo=UTC)
            lead = (event_time - moment).total_seconds() / 3600.0
            if 0 < lead <= lead_max_hours:
                earliest = moment if earliest is None else min(earliest, moment)
        if earliest is None:
            continue
        hits += 1
        leads.append((event_time - earliest).total_seconds() / 3600.0)

    # FAR per **cella-giorno di allerta**, e non per episodio.
    #
    # L'episodio sembrava l'unità giusta — una tempesta è un avviso, non
    # trenta — ma giudicarlo dal giorno in cui comincia sbaglia proprio i casi
    # che contano: un'allerta accesa per diciotto giorni è un episodio che
    # inizia il 3 aprile, e l'acqua arrivata il 17 cade fuori dalle sue 72 h.
    # Sul Piemonte dava 12 hit e 0 episodi veri: due numeri che non possono
    # stare insieme. La cella-giorno non ha bordi da sbagliare, ed è anche il
    # carico che l'operatore sopporta davvero — la stessa quantità che il
    # governo degli alert (#59) limita.
    #
    # Un giorno di allerta entra nel FAR solo se **qualcuno ha guardato**:
    # dentro una maschera EMS l'assenza di poligono allagato è un "non
    # allagato" osservato, fuori non è informazione. Senza la distinzione il
    # Piemonte misurava FAR 100% con 10.021 avvisi contro 12 celle di verità,
    # perché EMSR800 aveva mappato 0,3 km².
    true_days = 0
    false_days = 0
    unverifiable = 0
    episodes = 0
    for cell_id, days_alert in tally.alert_days.items():
        flooded_at = tally.truth.get(cell_id)
        passes = observed.get(cell_id, ())
        previous: date | None = None
        for day in sorted(set(days_alert)):
            if previous is None or (day - previous).days > 1:
                episodes += 1
            previous = day
            moment = datetime.combine(day, time(0, 0), tzinfo=UTC)
            deadline = moment + timedelta(hours=lead_max_hours)
            if flooded_at is not None and moment < flooded_at <= deadline:
                true_days += 1
            elif any(moment < when <= deadline for when in passes):
                false_days += 1
            else:
                unverifiable += 1

    hit_rate = hits / len(tally.truth) if tally.truth else 0.0
    verifiable = true_days + false_days
    return FloodBacktestMetrics(
        aoi_id=aoi_id,
        mode=mode,
        truth_cells=len(tally.truth),
        days=tally.days,
        cells_scored=cells_scored,
        hits=hits,
        misses=len(tally.truth) - hits,
        alert_episodes=episodes,
        true_days=true_days,
        false_days=false_days,
        unverifiable_days=unverifiable,
        hit_rate=hit_rate,
        far=false_days / verifiable if verifiable else 0.0,
        mean_lead_hours=sum(leads) / len(leads) if leads else 0.0,
        base_rate=(
            tally.truth_alert_days / tally.truth_cell_days if tally.truth_cell_days else 0.0
        ),
        pluvial_driven=tally.pluvial_driven,
        fluvial_driven=tally.fluvial_driven,
        measurable=tally.measurable,
        window_start=window_start,
    )


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def _write_report(
    *,
    aoi_id: str,
    start: datetime,
    end: datetime,
    runs: Sequence[FloodBacktestMetrics],
    provenance: dict[str, str],
    activations: Sequence[ActivationSummary],
    thresholds: FloodThresholds,
) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"backtest_flood_{aoi_id}_{start.date()}_{end.date()}.md"

    lines = [
        f"# Backtest alluvione — AOI `{aoi_id}`",
        "",
        f"Finestra: **{start.date()} → {end.date()}**  ",
        f"Generato: {datetime.now(UTC).isoformat(timespec='seconds')}  ",
        f"Soglie: `{thresholds.model_version}` "
        f"({thresholds.pluvial.threshold_mm:.0f}-{thresholds.pluvial.saturation_mm:.0f} mm/"
        f"{thresholds.pluvial.window_hours} h)",
        "",
        "## Truth set",
        "",
        f"- Fonte: **{provenance['source']}**",
        f"- Licenza: {provenance['licence']}",
        f"- Credenziali richieste: **{provenance['credentials']}**",
        f"- Geometria: {provenance['geometry']}",
        f"- Copertura: {provenance['coverage_note']}",
        "",
        f"> **Limite noto.** {provenance['known_limit']}",
        "",
    ]
    if activations:
        lines += [
            "| Attivazione | Data evento | Poligoni | Area allagata (km²) |",
            "|---|---|---:|---:|",
        ]
        for row in activations:
            lines.append(
                f"| `{row.activation_code}` | {row.event_time.date()} "
                f"| {row.polygons} | {row.area_km2:.1f} |"
            )
        lines.append("")

    lines += [
        "## Metriche",
        "",
        "| Replica | Dal | Hit rate | Tasso di base | Rapporto | FAR | Preavviso | "
        "Giorni-cella (veri/falsi/non verif.) | Avvisi |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for run in runs:
        if not run.measurable:
            lines.append(f"| `{run.mode}` | - | non misurabile | - | - | - | - | - | - |")
            continue
        ratio = run.hit_rate / run.base_rate if run.base_rate > 0 else float("inf")
        verifiable = run.true_days + run.false_days
        far_cell = f"{run.far:.0%}" if verifiable else "niente di verificabile"
        lines.append(
            f"| `{run.mode}` | {run.window_start or '-'} "
            f"| {run.hit_rate:.0%} | {run.base_rate:.0%} | "
            f"{ratio:.2f}x | {far_cell} | {run.mean_lead_hours:.0f} h "
            f"| {run.true_days} / {run.false_days} / {run.unverifiable_days} "
            f"| {run.alert_episodes} |"
        )
    lines += [
        "",
        "Le due repliche sono misurate sulla **stessa finestra**, altrimenti "
        "non sarebbero confrontabili: l'archivio delle previsioni emesse "
        "comincia nel febbraio 2024, e senza il taglio `observed` "
        "includerebbe eventi che `issued` non può vedere. Con "
        "`LIMEN_BACKTEST_FLOOD_MODE=observed` da sola la finestra resta "
        "intera e copre tutto il catalogo.",
        "",
        "`issued` è la previsione **come fu emessa** — la skill operativa. "
        "`observed` è la pioggia poi caduta: il tetto con una previsione "
        "perfetta, non un risultato. La distanza fra le due dice se conviene "
        "ritarare le soglie o migliorare il dato in ingresso.",
        "",
        "Il **tasso di base** è la quota di giornate in cui una cella poi "
        "allagata era in allerta comunque: è il metro dell'hit rate, e il "
        "rapporto fra i due è quanto il modello discrimina davvero.",
        "",
        "Il **FAR è per cella-giorno di allerta**: è il carico che un "
        "operatore sopporta davvero, e non ha i bordi sbagliati "
        "dell'episodio — un'allerta accesa per diciotto giorni è un episodio "
        "che comincia il primo, e l'evento del diciassettesimo cadrebbe fuori "
        "dalle sue 72 h.",
        "",
        "**Ambito.** Sono valutate solo le celle allagate e quelle dentro una "
        "maschera di osservazione: una cella che non è né l'una né l'altra "
        "produce solo giorni non verificabili, già fuori da ogni "
        "denominatore, quindi escluderla non cambia nessuna metrica.",
        "",
        "Un giorno di allerta entra nel FAR solo se **qualcuno ha guardato**: dentro "
        "una maschera di osservazione EMS l'assenza di poligono allagato è un "
        '"non allagato" osservato, fuori non è informazione. Gli episodi '
        "*non verificabili* restano contati e fuori dal denominatore, come "
        "`non verificabile` nel protocollo FAR degli alert. Contarli fra i "
        "falsi darebbe un FAR del 100% ogni volta che il satellite ha mappato "
        "una frazione dell'area allertata.",
        "",
    ]
    gate = thresholds.calibration.backtest if thresholds.calibration else None
    if gate is not None:
        lines += ["### Gate §2.5", ""]
        for run in runs:
            if not run.measurable:
                continue
            verifiable = run.true_days + run.false_days
            checks = [
                ("hit rate", run.hit_rate, gate.hit_rate_min, run.hit_rate >= gate.hit_rate_min),
                # Il FAR si giudica solo se c'è un denominatore osservato:
                # senza, "0%" sarebbe un gate superato per assenza di prove.
                (
                    "FAR",
                    run.far,
                    gate.far_max,
                    run.far <= gate.far_max if verifiable else None,
                ),
                (
                    "preavviso",
                    run.mean_lead_hours,
                    gate.lead_time_hours_min,
                    run.mean_lead_hours >= gate.lead_time_hours_min,
                ),
            ]
            verdicts = ", ".join(
                f"{name} " + ("PASS" if ok else "non valutabile" if ok is None else "FAIL")
                for name, _value, _target, ok in checks
            )
            lines.append(f"- `{run.mode}`: {verdicts}")
        lines.append("")

    for run in runs:
        if run.measurable:
            window = (
                f" (dal {run.window_start})"
                if run.window_start and run.window_start != start.date()
                else ""
            )
            lines.append(
                f"- `{run.mode}`{window}: {run.truth_cells} celle di verità, "
                f"{run.cells_scored} celle valutate su {run.days} giorni, "
                f"{run.hits} hit / {run.misses} mancati; "
                f"{run.alert_episodes} avvisi distinti "
                f"({run.pluvial_driven} da pioggia, {run.fluvial_driven} da portata), "
                f"{run.true_days + run.false_days} giorni-cella verificabili "
                f"su {run.true_days + run.false_days + run.unverifiable_days}."
            )
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def _parse_dt(name: str) -> datetime | None:
    raw = os.getenv(name)
    if not raw:
        return None
    parsed = datetime.fromisoformat(raw)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _parse_level() -> RiskLevel:
    raw = os.getenv(_LEVEL_ENV)
    if not raw:
        return RiskLevel.High
    try:
        return RiskLevel(raw)
    except ValueError:
        log.warning("backtest_flood.bad_level", value=raw)
        return RiskLevel.High


def _modes() -> list[Mode]:
    raw = (os.getenv(_MODE_ENV) or "both").strip().lower()
    if raw == "issued":
        return ["issued"]
    if raw == "observed":
        return ["observed"]
    return ["issued", "observed"]


async def run() -> int:
    thresholds = load_hazard_thresholds(HazardType.FLOOD)
    assert isinstance(thresholds, FloodThresholds)
    alert_level = _parse_level()
    node_deg = float(os.getenv(_NODE_ENV, str(_DEFAULT_NODE_DEG)))
    modes = _modes()

    try:
        async with lifespan_pool():
            await run_migrations()
            single = os.getenv(_AOI_ENV)
            aois = [single] if single else await _aois_with_events()
            if not aois:
                log.warning(
                    "backtest_flood.no_truth",
                    note="esegui `limen ingest-events --hazard flood`",
                )
                return 0

            activations = await flood_events_repo.activations_summary()
            for aoi_id in aois:
                windows = await _event_windows(aoi_id)
                forced_start = _parse_dt(_START_ENV)
                forced_end = _parse_dt(_END_ENV)
                if forced_start and forced_end:
                    windows = [(forced_start, forced_end)]
                if not windows:
                    log.warning("backtest_flood.aoi.skipped", aoi_id=aoi_id, reason="nessun evento")
                    continue

                observed = await flood_events_repo.observation_times(aoi_id)
                span_truth = await flood_events_repo.truth_cells(
                    aoi_id,
                    start=min(w[0] for w in windows),
                    end=max(w[1] for w in windows),
                )
                keep = set(observed) | set(span_truth)
                cells = await _fetch_cells(aoi_id, floor=thresholds.susceptibility.floor, keep=keep)
                if not cells:
                    # Né celle allagate né celle osservate: non c'è niente da
                    # misurare, e un report di zeri sembrerebbe un risultato.
                    log.warning(
                        "backtest_flood.aoi.skipped",
                        aoi_id=aoi_id,
                        reason="nessuna cella verificabile",
                    )
                    continue
                nodes, cell_node = _nodes_from_cells(cells, spacing=node_deg)
                engine = FloodScoringEngine(thresholds)
                span_start = min(w[0] for w in windows)
                span_end = max(w[1] for w in windows)
                log.info(
                    "backtest_flood.aoi.loaded",
                    aoi_id=aoi_id,
                    observed_cells=len(observed),
                    truth_cells=len(span_truth),
                    cells=len(cells),
                    nodes=len(nodes),
                    windows=len(windows),
                    days=sum((w[1].date() - w[0].date()).days + 1 for w in windows),
                )

                # Chiedendo entrambe le repliche si chiede un **confronto**, e
                # un confronto fra finestre diverse non è un confronto:
                # `issued` esiste solo dal febbraio 2024, quindi senza questo
                # taglio `observed` includerebbe il maggio 2023 e uscirebbe
                # *peggio* del previsionale (misurato: 39% contro 77%), che
                # letto sulla stessa riga è un assurdo. Con `_MODE=observed` da
                # sola la finestra resta intera, perché lì la copertura
                # massima è ciò che si vuole.
                clip_all = len(modes) > 1
                runs: list[FloodBacktestMetrics] = []
                for mode in modes:
                    tally = _Tally.empty()
                    effective_start: date | None = None
                    for lo, hi in windows:
                        # `issued` si misura solo dove l'archivio delle
                        # previsioni emesse esiste. Senza questo taglio, un
                        # evento del maggio 2023 comparirebbe fra i mancati per
                        # assenza di dato e non per un limite del modello —
                        # cioè il backtest mentirebbe nella direzione più
                        # facile da non notare.
                        window_lo = lo
                        if clip_all or mode == "issued":
                            floor_dt = datetime.combine(
                                ISSUED_ARCHIVE_START, time(0, 0), tzinfo=UTC
                            )
                            window_lo = max(lo, floor_dt)
                        if window_lo > hi:
                            continue
                        effective_start = (
                            window_lo.date()
                            if effective_start is None
                            else min(effective_start, window_lo.date())
                        )
                        window_truth = await flood_events_repo.truth_cells(
                            aoi_id, start=window_lo, end=hi
                        )
                        series = await _fetch_node_series(
                            nodes, start=window_lo.date(), end=hi.date()
                        )
                        tally.merge(
                            _replay(
                                aoi_id=aoi_id,
                                mode=mode,
                                cells=cells,
                                cell_node=cell_node,
                                series=series,
                                truth=window_truth,
                                start=window_lo,
                                end=hi,
                                alert_level=alert_level,
                                thresholds=thresholds,
                                engine=engine,
                            )
                        )
                    if not tally.measurable:
                        runs.append(_unmeasurable(aoi_id, mode, days=tally.days))
                        continue
                    runs.append(
                        _metrics(
                            aoi_id=aoi_id,
                            mode=mode,
                            tally=tally,
                            observed=observed,
                            cells_scored=len(cells),
                            window_start=effective_start,
                            thresholds=thresholds,
                        )
                    )
                report = _write_report(
                    aoi_id=aoi_id,
                    start=span_start,
                    end=span_end,
                    runs=runs,
                    provenance=catalogue_provenance(),
                    activations=activations,
                    thresholds=thresholds,
                )
                for metrics in runs:
                    log.info(
                        "backtest_flood.aoi.done",
                        aoi_id=aoi_id,
                        mode=metrics.mode,
                        measurable=metrics.measurable,
                        truth_cells=metrics.truth_cells,
                        hit_rate=round(metrics.hit_rate, 4),
                        base_rate=round(metrics.base_rate, 4),
                        far=round(metrics.far, 4),
                        unverifiable_days=metrics.unverifiable_days,
                        pluvial_driven=metrics.pluvial_driven,
                        fluvial_driven=metrics.fluvial_driven,
                        mean_lead_hours=round(metrics.mean_lead_hours, 1),
                        report=str(report),
                    )
    finally:
        await SharedHttpClient.aclose()
    return 0


def main() -> int:
    import asyncio

    return asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
