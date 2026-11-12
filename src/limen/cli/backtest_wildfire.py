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
* ``LIMEN_BACKTEST_WILDFIRE_VERITA`` — ``effis`` (default), ``catasti`` o
  ``tutte``: i perimetri EFFIS, i catasti regionali degli incendi (#498: gli
  incendi piccoli, Basilicata, Sardegna, Emilia-Romagna) o entrambi.
* ``LIMEN_BACKTEST_WILDFIRE_ETTARI`` — ``min-max`` in ettari (un estremo può
  mancare: ``-10``, ``100-``): solo gli incendi di quella superficie, per
  leggere il backtest per classe di grandezza.
* ``LIMEN_BACKTEST_WILDFIRE_PIOGGIA`` — ``modello`` (default) o ``osservata``:
  la pioggia delle 24 ore fino a mezzogiorno dal «Merging» DPC archiviato
  (``RADAR_ARCHIVE__CARTELLA``) al posto di quella del modello, dove il radar
  l'ha misurata. È la correzione del passo notturno ``fwi_pioggia_osservata``.

Accanto all'hit rate il report dà il **carico meteo**: la quota di
giornate-nodo della stagione con FWI in fascia alta o oltre. Le celle bruciate
dicono se l'allerta c'era; il carico dice quante allerte c'erano in tutto, e
quindi quante sono rumore per chi le riceve.

Il carico meteo non vede il terreno, e il tasso di base guarda solo le celle
bruciate: nessuno dei due si accorge di un peso del combustibile che accende
mezza regione (#295). Lo fa il **carico per cella**: la quota di
giornate-cella della stagione, su **tutte** le celle dell'AOI, in allerta. Il
rapporto fra hit rate e carico per cella è la discriminazione spaziale, lo
stesso metro del backtest frane: alzare un peso fa salire l'hit rate, ma se fa
salire il carico altrettanto non ha insegnato niente.

Sullo stesso conto si misurano i **falsi allarmi** (#479): una giornata-cella
in allerta è vera se la sua cella brucia entro l'orizzonte di preavviso, falsa
altrimenti. Senza ``LIMEN_BACKTEST_WILDFIRE_AOI`` il comando gira su tutte le
AOI e scrive anche ``backtest_wildfire_italia_<inizio>_<fine>.md``, una riga per
regione con il totale pesato sulle celle bruciate.
"""

from __future__ import annotations

import os
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import numpy as np
from fwi_chain import FwiState, advance

from limen.cli import provenienza
from limen.cli.fwi_backfill import params_from
from limen.config.settings import get_settings
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
from limen.data.db import acquire, lifespan_pool
from limen.data.repos.aoi_repo import list_aoi_ids
from limen.integrations._http import SharedHttpClient
from limen.integrations.dpc.fwi_pioggia import Fonte, fonte_archivio
from limen.integrations.dpc.merging_archive import MergingArchive
from limen.integrations.openmeteo.client import OpenMeteoHttpClient
from limen.integrations.openmeteo.dtos import MeteoSnapshot
from limen.integrations.openmeteo.grid import build_snapped_nodes, nearest_node

log = get_logger(__name__)

#: Dove finisce il report. Configurabile con `LIMEN_REPORTS_DIR` perche'
#: dentro un container la directory di lavoro non e' scrivibile.
REPORTS_DIR = Path(os.getenv("LIMEN_REPORTS_DIR", "reports"))

_AOI_ENV = "LIMEN_BACKTEST_WILDFIRE_AOI"
_START_ENV = "LIMEN_BACKTEST_WILDFIRE_START"
_END_ENV = "LIMEN_BACKTEST_WILDFIRE_END"
_LEVEL_ENV = "LIMEN_BACKTEST_WILDFIRE_LEVEL"
_PIOGGIA_ENV = "LIMEN_BACKTEST_WILDFIRE_PIOGGIA"
_VERITA_ENV = "LIMEN_BACKTEST_WILDFIRE_VERITA"
_ETTARI_ENV = "LIMEN_BACKTEST_WILDFIRE_ETTARI"

_TABELLE_VERITA = {
    "effis": ("fire_perimeters",),
    "catasti": ("catasti_incendi",),
    "tutte": ("fire_perimeters", "catasti_incendi"),
}
_NOMI_VERITA = {
    "effis": "perimetri EFFIS",
    "catasti": "catasti regionali degli incendi",
    "tutte": "perimetri EFFIS e catasti regionali",
}


@dataclass(frozen=True, slots=True)
class Verita:
    """Quali incendi fanno da verità, e di che grandezza."""

    fonte: str = "effis"
    ettari_min: float | None = None
    ettari_max: float | None = None

    @property
    def descrizione(self) -> str:
        testo = _NOMI_VERITA[self.fonte]
        if self.ettari_min is None and self.ettari_max is None:
            return testo
        lo = f"{self.ettari_min:g}" if self.ettari_min is not None else "0"
        hi = f"{self.ettari_max:g} ha" if self.ettari_max is not None else "ha e oltre"
        return f"{testo}, incendi da {lo} a {hi}"

    @property
    def suffisso(self) -> str:
        parti = [] if self.fonte == "effis" else [self.fonte]
        if self.ettari_min is not None or self.ettari_max is not None:
            lo = f"{self.ettari_min:g}" if self.ettari_min is not None else ""
            hi = f"{self.ettari_max:g}" if self.ettari_max is not None else ""
            parti.append(f"{lo}-{hi}ha")
        return "".join(f"_{p}" for p in parti)


def leggi_verita(fonte: str, ettari: str) -> Verita:
    """La verità dalle due variabili; ``ValueError`` se non si leggono."""
    if fonte not in _TABELLE_VERITA:
        raise ValueError(f"{_VERITA_ENV}={fonte!r}: atteso effis, catasti o tutte")
    if not ettari.strip():
        return Verita(fonte=fonte)
    lo, sep, hi = ettari.partition("-")
    if not sep:
        raise ValueError(f"{_ETTARI_ENV}={ettari!r}: atteso min-max")
    return Verita(
        fonte=fonte,
        ettari_min=float(lo) if lo.strip() else None,
        ettari_max=float(hi) if hi.strip() else None,
    )


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
    #: Quota di giornate-nodo della stagione con FWI in fascia alta o oltre,
    #: su tutta l'AOI: quante allerte meteo c'erano, bruciato o no.
    carico_meteo: float = 0.0
    pioggia: str = "modello"
    #: Quota di giornate-cella della stagione in allerta, su tutte le celle
    #: dell'AOI: quanto territorio il modello accende, bruciato o no.
    carico_celle: float = 0.0
    picco_celle: float = 0.0
    giorno_picco: date | None = None
    #: Vero quando il FAR viene dal carico per cella (#479): giornate-cella in
    #: allerta su celle che non hanno bruciato entro l'orizzonte.
    far_misurato: bool = False


def _at_least(level: RiskLevel, threshold: RiskLevel) -> bool:
    return _LEVEL_ORDER.index(level) >= _LEVEL_ORDER.index(threshold)


async def fetch_burnt_cells(
    aoi_id: str, *, start: date, end: date, verita: Verita | None = None
) -> dict[str, tuple[date, float, float]]:
    """``{cell_id: (fire_date, lon, lat)}`` for cells inside a burnt perimeter.

    The earliest fire per cell is the anchor: a cell that burned twice in the
    window is one truth event, not two, or a single well-warned area would
    inflate the hit rate by however often it caught fire.
    """
    verita = verita or Verita()
    # Nomi di tabella da un dizionario chiuso, mai dall'ambiente.
    incendi = " UNION ALL ".join(
        f"SELECT fire_date, area_ha, geom FROM {t}" for t in _TABELLE_VERITA[verita.fonte]
    )
    async with acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT g.id AS cell_id,
                   MIN(p.fire_date) AS first_fire,
                   ST_X(ST_Centroid(g.geom)) AS lon,
                   ST_Y(ST_Centroid(g.geom)) AS lat
            FROM ({incendi}) p
            JOIN grid_cells g ON ST_Intersects(g.geom, p.geom)
            WHERE g.aoi_id = $1
              AND p.fire_date IS NOT NULL
              AND p.fire_date >= $2
              AND p.fire_date <= $3
              AND ($4::float8 IS NULL OR p.area_ha >= $4)
              AND ($5::float8 IS NULL OR p.area_ha < $5)
            GROUP BY g.id, g.geom
            """,
            aoi_id,
            start,
            end,
            verita.ettari_min,
            verita.ettari_max,
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
    pioggia: dict[date, float | None] | None = None,
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
        obs = snapshot.noon_observation(day, noon_hour=thresholds.fwi.ora_osservazione_utc)
        if obs is None:
            continue
        step = advance(
            state,
            month=day.month,
            temperature_c=obs.temperature_c,
            relative_humidity_pct=obs.relative_humidity_pct,
            wind_speed_kmh=obs.wind_speed_kmh,
            rain_24h_mm=(
                oss
                if pioggia is not None and (oss := pioggia.get(day)) is not None
                else obs.rain_24h_mm
            ),
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
    # falsi allarmi sono sempre zero: si contano su tutte le celle dell'AOI in
    # `carico_celle` (#479), che `backtest_aoi` riporta nelle metriche.
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


def carico_meteo(
    chains: list[dict[date, FireWeatherState]],
    *,
    start: date,
    end: date,
    thresholds: WildfireThresholds,
) -> float:
    """Quota di giornate-nodo in ``[start, end]`` con FWI in fascia alta o oltre.

    Il FWI normalizzato contro il cutoff «alto»: è il pericolo meteo che una
    cella di conifere su pendio saturo riceverebbe pieno, quindi il tetto del
    numero di allerte che il meteo da solo può accendere.
    """
    soglia = thresholds.classes.high.lo * thresholds.fwi.normalisation_max
    giorni = [s for c in chains for d, s in c.items() if start <= d <= end]
    return sum(1 for s in giorni if s.fwi >= soglia) / len(giorni) if giorni else 0.0


@dataclass(frozen=True, slots=True)
class CellaAoi:
    cell_id: str
    lon: float
    lat: float
    static: StaticFactors


async def celle_aoi(aoi_id: str) -> list[CellaAoi]:
    """Ogni cella dell'AOI con i fattori che il motore legge."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT g.id AS cell_id,
                   ST_X(ST_Centroid(g.geom)) AS lon, ST_Y(ST_Centroid(g.geom)) AS lat,
                   s.landuse_code, s.slope_deg
              FROM grid_cells g
              LEFT JOIN cell_static_factors s ON s.cell_id = g.id
             WHERE g.aoi_id = $1
            """,
            aoi_id,
        )
    return [
        CellaAoi(
            cell_id=str(r["cell_id"]),
            lon=float(r["lon"]),
            lat=float(r["lat"]),
            static=StaticFactors(
                cell_id=str(r["cell_id"]),
                landuse_code=r["landuse_code"],
                slope_deg=r["slope_deg"],
            ),
        )
        for r in rows
    ]


def _soglia(level: RiskLevel, thresholds: WildfireThresholds) -> float:
    c = thresholds.classes
    return {
        RiskLevel.None_: c.none.lo,
        RiskLevel.Low: c.low.lo,
        RiskLevel.Moderate: c.moderate.lo,
        RiskLevel.High: c.high.lo,
        RiskLevel.VeryHigh: c.very_high.lo,
    }[level]


@dataclass(frozen=True, slots=True)
class CaricoCelle:
    #: Quota di giornate-cella della stagione in allerta, su tutta l'AOI.
    quota: float
    #: La quota più alta di celle dell'AOI in allerta nello stesso giorno, e
    #: quel giorno. La media stagionale non vede il giorno in cui il rosso
    #: copre mezza regione: chi riceve le notifiche sì (#301).
    picco: float
    giorno_picco: date | None
    #: Falsi allarmi per giornata-cella (#479): la quota delle giornate-cella in
    #: allerta su una cella che **non** ha bruciato entro l'orizzonte di
    #: preavviso. ``None`` senza allerte, o senza le date degli incendi.
    far: float | None = None
    giornate_allerta: int = 0
    giornate_false: int = 0


def carico_celle(
    celle: list[CellaAoi],
    *,
    nodes: list[tuple[float, float]],
    chains: list[dict[date, FireWeatherState]],
    start: date,
    end: date,
    thresholds: WildfireThresholds,
    alert_level: RiskLevel,
    bruciate: Mapping[str, date] | None = None,
) -> CaricoCelle:
    """Le giornate-cella in ``[start, end]`` con la cella in ``alert_level``
    o oltre, su tutte le celle dell'AOI: in media e nel giorno peggiore.

    Con ``bruciate`` (``{cell_id: giorno del primo incendio}``) conta anche i
    **falsi allarmi** (#479): un'allerta è vera se la sua cella brucia entro
    l'orizzonte di preavviso dopo quel giorno, la stessa finestra dell'hit
    rate; ogni altra è falsa. Con i perimetri EFFIS (incendi grandi) è un
    numero alto per costruzione: dice quante allerte riceve chi le riceve per
    ogni incendio che arriva davvero.

    Il punteggio è ``min(fwi_norm * terreno, 1)``: il terreno di una cella si
    chiede al motore una volta sola, con il meteo al massimo (``fwi_norm`` = 1),
    e poi si moltiplica per i giorni del suo nodo. Stesso conto del motore,
    senza i milioni di valutazioni di un replay cella per cella. Il rosso dalla
    banda FWI (``very_high``) dipende dal FWI del giorno, quindi il terreno si
    chiede senza e la soglia si applica qui, giorno per giorno.
    """
    engine = WildfireScoringEngine(thresholds.model_copy(update={"very_high": None}))
    gate = thresholds.very_high
    rosso = thresholds.classes.very_high.lo
    pieno = thresholds.fwi.normalisation_max
    soglia = _soglia(alert_level, thresholds)
    per_nodo: dict[int, list[float]] = defaultdict(list)
    fuoco_per_nodo: dict[int, list[date | None]] = defaultdict(list)
    orizzonte = timedelta(days=int(_LEAD_MAX_HOURS // 24))
    for cella in celle:
        terreno = engine.score(
            CellFeatureBundle(
                aoi_id="carico",
                cell_id=cella.cell_id,
                static=cella.static,
                dynamic=DynamicInputs(
                    valuation_time=datetime.combine(start, time(12), UTC),
                    fire_weather=FireWeatherState(
                        day=start, ffmc=0, dmc=0, dc=0, isi=0, bui=0, fwi=pieno, chain_days=0
                    ),
                ),
            )
        ).score
        k = nearest_node(cella.lon, cella.lat, nodes)
        per_nodo[k].append(terreno)
        fuoco_per_nodo[k].append((bruciate or {}).get(cella.cell_id))
    giornate = 0
    in_allerta = 0
    vere = 0
    per_giorno: dict[date, int] = defaultdict(int)
    for k, terreni in per_nodo.items():
        stati = [(d, s.fwi) for d, s in chains[k].items() if start <= d <= end]
        if not stati:
            continue
        fwi = np.array([v for _, v in stati])
        t = np.array(terreni)
        punteggi = np.minimum(np.outer(t, np.minimum(fwi / pieno, 1.0)), 1.0)
        if gate is not None:
            accesa = np.outer(t >= gate.terrain_min, fwi >= gate.fwi_min)
            punteggi = np.where(accesa, np.maximum(punteggi, rosso), punteggi)
        accese = punteggi >= soglia
        allerte = np.count_nonzero(accese, axis=0)
        for riga, fuoco in enumerate(fuoco_per_nodo[k]):
            if fuoco is None:
                continue
            vere += sum(
                1
                for (d, _), on in zip(stati, accese[riga], strict=True)
                if on and d <= fuoco <= d + orizzonte
            )
        giornate += punteggi.size
        in_allerta += int(allerte.sum())
        for (d, _), n in zip(stati, allerte, strict=True):
            per_giorno[d] += int(n)
    if not giornate:
        return CaricoCelle(quota=0.0, picco=0.0, giorno_picco=None)
    giorno, n = max(per_giorno.items(), key=lambda kv: (kv[1], kv[0]))
    return CaricoCelle(
        quota=in_allerta / giornate,
        picco=n / sum(len(t) for t in per_nodo.values()),
        giorno_picco=giorno if n else None,
        far=(in_allerta - vere) / in_allerta if bruciate is not None and in_allerta else None,
        giornate_allerta=in_allerta,
        giornate_false=in_allerta - vere if bruciate is not None else 0,
    )


def _lift(metrics: WildfireBacktestMetrics) -> float:
    """Quante volte l'hit rate supera il tasso di base. 0 se non misurabile."""
    return metrics.hit_rate / metrics.base_rate if metrics.base_rate > 0 else 0.0


def _lift_spaziale(metrics: WildfireBacktestMetrics) -> float:
    """Quante volte l'hit rate supera il carico per cella. 0 se non misurabile."""
    return metrics.hit_rate / metrics.carico_celle if metrics.carico_celle > 0 else 0.0


def write_report(
    metrics: WildfireBacktestMetrics,
    *,
    start: date,
    end: date,
    alert_level: RiskLevel,
    verita: Verita | None = None,
) -> Path:
    verita = verita or Verita()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"backtest_wildfire_{metrics.aoi_id}_{start}_{end}{verita.suffisso}.md"
    lines = [
        f"# Limen backtest incendio — AOI `{metrics.aoi_id}`",
        "",
        f"Finestra: **{start} → {end}**",
        f"Generato: {datetime.now(UTC).isoformat()}",
        f"Pioggia della catena: **{metrics.pioggia}**",
        f"Soglia di allerta: **{alert_level.value}**, "
        f"orizzonte di preavviso **{_LEAD_MAX_HOURS:.0f} h**",
        "",
        f"- Celle bruciate ({verita.descrizione} nella finestra): **{metrics.truth_fires}**",
        f"- Celle con almeno un'allerta: **{metrics.cells_warned}**",
        f"- Hit: **{metrics.hits}**, mancati: **{metrics.misses}** (celle bruciate); "
        f"falsi allarmi: **{metrics.false_alarms}** giornate-cella",
        "",
        "## Metriche §2.5",
        "",
        f"- **Hit rate**: {metrics.hit_rate:.2%}",
        f"- **Tasso di base**: {metrics.base_rate:.2%} "
        f"(quota di giornate in allerta a prescindere dagli incendi)",
        f"- **Discriminazione**: {_lift(metrics):.2f} volte il tasso di base",
        f"- **Carico meteo**: {metrics.carico_meteo:.2%} delle giornate-nodo della "
        "stagione con FWI in fascia alta o oltre",
        f"- **Carico per cella**: {metrics.carico_celle:.2%} delle giornate-cella della "
        "stagione in allerta, su tutte le celle dell'AOI",
        f"- **Discriminazione spaziale**: {_lift_spaziale(metrics):.2f} volte il carico per cella",
        f"- **Giorno peggiore**: {metrics.picco_celle:.2%} delle celle dell'AOI in allerta "
        f"insieme ({metrics.giorno_picco or 'nessuno'})",
        (
            f"- **FAR per giornata-cella**: {metrics.far:.2%} delle giornate-cella in "
            f"allerta su celle che non hanno bruciato nelle {_LEAD_MAX_HOURS:.0f} h seguenti"
            if metrics.far_misurato
            else "- **FAR**: non misurato (nessuna giornata-cella in allerta)"
        ),
        f"- **Preavviso medio**: {metrics.mean_lead_hours:.1f} h",
        "",
        "> L'hit rate da solo non dice nulla: un modello che dichiara pericolo",
        "> alto tutti i giorni d'estate lo massimizza senza discriminare. Il",
        "> confronto con il tasso di base è ciò che separa la bravura dalla",
        "> frequenza — sotto 1.0 il modello è peggio del caso.",
        "> Hit rate e preavviso guardano le celle che hanno bruciato, nelle",
        f"> {_LEAD_MAX_HOURS:.0f} h prima di ciascun incendio. Il FAR guarda **tutte** le",
        "> celle dell'AOI per tutta la stagione: un'allerta è falsa se la sua cella",
        "> non brucia nell'orizzonte di preavviso. Con i perimetri EFFIS, che",
        "> censiscono gli incendi grandi, è alto per costruzione: si legge come",
        "> quante allerte arrivano per ogni incendio vero, e si confronta fra",
        "> varianti, non con lo zero.",
        "",
    ]
    if metrics.truth_fires == 0:
        lines.insert(
            5,
            f"> **Nessun incendio ({verita.descrizione}) nella finestra.** Le "
            "sorgenti sono pubbliche e non richiedono credenziali: se la tabella "
            "è vuota va eseguito l'ingest (`limen effis-sync`, `limen "
            "catasti-incendi`). Le metriche sotto sono vuote per costruzione, "
            "non zero.",
        )
    provenienza.scrivi_report(out, "\n".join(lines))
    return out


def write_national_report(
    risultati: Sequence[WildfireBacktestMetrics],
    *,
    start: date,
    end: date,
    alert_level: RiskLevel,
    verita: Verita | None = None,
) -> Path:
    """Una riga per regione, sulla stessa finestra e la stessa soglia (#479).

    I totali in fondo sono **pesati sulle celle bruciate** per hit rate e tasso
    di base, non una media delle righe: una regione con tre incendi non pesa
    quanto una con trecento.
    """
    verita = verita or Verita()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"backtest_wildfire_italia_{start}_{end}{verita.suffisso}.md"
    righe = [
        "# Limen backtest incendio — Italia",
        "",
        f"Finestra: **{start} → {end}**; soglia di allerta **{alert_level.value}**, "
        f"orizzonte di preavviso **{_LEAD_MAX_HOURS:.0f} h**; verità: "
        f"{verita.descrizione}. Il dettaglio di ogni regione è nel suo report.",
        "",
        "| AOI | celle bruciate | hit rate | tasso di base | discriminazione "
        "| carico per cella | FAR (giornate-cella) | preavviso |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for m in sorted(risultati, key=lambda m: m.aoi_id):
        if m.truth_fires == 0:
            righe.append(f"| `{m.aoi_id}` | 0 | — | — | — | {m.carico_celle:.1%} | — | — |")
            continue
        far = f"{m.far:.1%}" if m.far_misurato else "—"
        righe.append(
            f"| `{m.aoi_id}` | {m.truth_fires} | {m.hit_rate:.0%} | {m.base_rate:.0%} "
            f"| {_lift(m):.2f}x | {m.carico_celle:.1%} | {far} | {m.mean_lead_hours:.0f} h |"
        )
    fuochi = sum(m.truth_fires for m in risultati)
    if fuochi:
        hit = sum(m.hit_rate * m.truth_fires for m in risultati) / fuochi
        base = sum(m.base_rate * m.truth_fires for m in risultati) / fuochi
        righe.append(
            f"| **Italia** | **{fuochi}** | **{hit:.0%}** | **{base:.0%}** "
            f"| **{hit / base if base else 0:.2f}x** | | | |"
        )
    righe += [
        "",
        "Una regione senza celle bruciate non ha hit rate né FAR: non è «zero»,",
        f"è nessun incendio censito ({verita.descrizione}) nella finestra.",
    ]
    provenienza.scrivi_report(out, "\n".join(righe))
    return out


async def backtest_aoi(
    *,
    aoi_id: str,
    start: date,
    end: date,
    alert_level: RiskLevel,
    thresholds: WildfireThresholds,
    client: OpenMeteoHttpClient,
    fonte: Fonte | None = None,
    verita: Verita | None = None,
) -> WildfireBacktestMetrics:
    truth = await fetch_burnt_cells(aoi_id, start=start, end=end, verita=verita)
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
        path = write_report(metrics, start=start, end=end, alert_level=alert_level, verita=verita)
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
    osservata: list[dict[date, float | None]] = [{} for _ in nodes]
    if fonte is not None:
        for day in days:
            for k, mm in enumerate(await fonte(nodes, day)):
                osservata[k][day] = mm
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
            pioggia=osservata[k] if fonte is not None else None,
        )
        for k, ((lon, lat), samples) in enumerate(zip(nodes, series, strict=True))
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
    carico = carico_celle(
        await celle_aoi(aoi_id),
        nodes=nodes,
        chains=chains,
        start=start,
        end=end,
        thresholds=thresholds,
        alert_level=alert_level,
        bruciate={cella: giorno for cella, (giorno, _lon, _lat) in truth.items()},
    )
    metrics = replace(
        metrics,
        far=carico.far if carico.far is not None else 0.0,
        false_alarms=carico.giornate_false,
        far_misurato=carico.far is not None,
        carico_meteo=carico_meteo(chains, start=start, end=end, thresholds=thresholds),
        carico_celle=carico.quota,
        picco_celle=carico.picco,
        giorno_picco=carico.giorno_picco,
        pioggia="osservata" if fonte is not None else "modello",
    )
    path = write_report(metrics, start=start, end=end, alert_level=alert_level, verita=verita)
    log.info(
        "backtest_wildfire.aoi.done",
        aoi_id=aoi_id,
        truth_fires=metrics.truth_fires,
        hit_rate=round(metrics.hit_rate, 4),
        far=round(metrics.far, 4),
        mean_lead_hours=round(metrics.mean_lead_hours, 1),
        base_rate=round(metrics.base_rate, 4),
        lift=round(_lift(metrics), 2),
        carico_meteo=round(metrics.carico_meteo, 4),
        carico_celle=round(metrics.carico_celle, 4),
        picco_celle=round(metrics.picco_celle, 4),
        lift_spaziale=round(_lift_spaziale(metrics), 2),
        pioggia=metrics.pioggia,
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

    try:
        verita = leggi_verita(os.getenv(_VERITA_ENV, "effis"), os.getenv(_ETTARI_ENV, ""))
    except ValueError as exc:
        log.error("backtest_wildfire.bad_env", error=str(exc))
        return 1

    fonte: Fonte | None = None
    pioggia = os.getenv(_PIOGGIA_ENV, "modello")
    if pioggia == "osservata":
        archivio = get_settings().radar_archive
        if not archivio.attivo:
            log.error("backtest_wildfire.archivio_non_configurato", hint="RADAR_ARCHIVE__CARTELLA")
            return 1
        fonte = fonte_archivio(MergingArchive(Path(archivio.cartella)))
    elif pioggia != "modello":
        log.error("backtest_wildfire.bad_env", var=_PIOGGIA_ENV, value=pioggia)
        return 1

    client = OpenMeteoHttpClient()
    async with lifespan_pool():
        one = os.getenv(_AOI_ENV)
        aoi_ids = [one] if one else await list_aoi_ids()
        if not aoi_ids:
            log.warning("backtest_wildfire.no_aoi")
            return 0
        risultati = [
            await backtest_aoi(
                aoi_id=aoi_id,
                start=start,
                end=end,
                alert_level=alert_level,
                thresholds=loaded,
                client=client,
                fonte=fonte,
                verita=verita,
            )
            for aoi_id in aoi_ids
        ]
    if len(risultati) > 1:
        nazionale = write_national_report(
            risultati, start=start, end=end, alert_level=alert_level, verita=verita
        )
        log.info("backtest_wildfire.italia.done", aoi=len(risultati), report=str(nazionale))
    await SharedHttpClient.aclose()
    return 0


__all__ = [
    "CaricoCelle",
    "CellaAoi",
    "Verita",
    "WildfireBacktestMetrics",
    "backtest_aoi",
    "carico_celle",
    "celle_aoi",
    "evaluate",
    "fetch_burnt_cells",
    "leggi_verita",
    "replay_chain",
    "run",
    "write_national_report",
    "write_report",
]
