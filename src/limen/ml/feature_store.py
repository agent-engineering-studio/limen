"""Offline feature-store extraction (V2).

Walks the IFFI inventory + a balanced background sample, reconstructs
the point-in-time-correct feature vector for each cell using the
existing :func:`assemble_bundles` path (so train/serve parity is
guaranteed), assigns a coarse spatial-block id for CV, and writes the
result to :sql:`training_samples`.

This module deliberately uses the same DTOs and aggregators the live
workflow uses — the only difference is that we replay history rather
than fetching the *current* meteo / seismic state.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import structlog
from shapely.geometry.base import BaseGeometry

from limen.config.settings import Settings, get_settings
from limen.core.logging import get_logger
from limen.core.models.hazard import DEFAULT_HAZARD, HazardType
from limen.core.models.risk import (
    CellFeatureBundle,
    DynamicInputs,
    FireWeatherState,
    RainfallSample,
    RainfallSeries,
    StaticFactors,
)
from limen.core.scoring.regional_thresholds import (
    WildfireThresholds,
    load_hazard_thresholds,
)
from limen.data.db import acquire
from limen.data.repos import (
    cell_insar_features_repo,
    cell_static_factors_repo,
    training_samples_repo,
)
from limen.data.repos.training_samples_repo import LabelSource, TrainingSample

_log: structlog.stdlib.BoundLogger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SpatialBlockGrid:
    """Coarse grid used to assign a CV block to each (lon, lat).

    Block id is ``"{lon_index}|{lat_index}"`` — stable, deterministic,
    and small enough that spatially-adjacent cells get the same block.
    """

    edge_deg: float

    def block_for(self, lon: float, lat: float) -> str:
        x = int(lon // self.edge_deg)
        y = int(lat // self.edge_deg)
        return f"{x}|{y}"


@dataclass(frozen=True, slots=True)
class _PositiveEvent:
    """One IFFI event, mapped to its containing grid cell."""

    iffi_id: str
    cell_id: str
    aoi_id: str
    occurrence_date: datetime
    centroid_lonlat: tuple[float, float]
    geom: BaseGeometry


async def _load_positives(*, min_occurrence: datetime) -> list[_PositiveEvent]:
    """Join dated landslide events (e-ITALICA) to their containing cells.

    The IFFI inventory carries no dates (occurrence_date is NULL across the
    GeoServer opendata), so labels come from ``landslide_events`` — the
    catalogue the §2.5 backtest validates against.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT e.id AS event_id,
                   g.id AS cell_id,
                   g.aoi_id,
                   e.event_time,
                   ST_X(ST_Centroid(g.geom)) AS lon,
                   ST_Y(ST_Centroid(g.geom)) AS lat,
                   e.geom
            FROM landslide_events e
            JOIN grid_cells g
              ON ST_Intersects(g.geom, e.geom)
            WHERE e.event_time >= $1
            ORDER BY e.event_time
            """,
            min_occurrence,
        )
    out: list[_PositiveEvent] = []
    for r in rows:
        out.append(
            _PositiveEvent(
                iffi_id=str(r["event_id"]),
                cell_id=str(r["cell_id"]),
                aoi_id=str(r["aoi_id"]),
                occurrence_date=r["event_time"],
                centroid_lonlat=(float(r["lon"]), float(r["lat"])),
                geom=r["geom"],
            )
        )
    return out


async def _load_flood_positives(*, min_occurrence: datetime) -> list[_PositiveEvent]:
    """Celle intersecate da un perimetro allagato osservato (Copernicus EMS).

    L'ancora è ``event_time`` (inizio dell'evento) e non l'acquisizione
    satellitare: un campione etichettato all'ora in cui il satellite ha visto
    l'acqua insegnerebbe al modello a riconoscere un allagamento in corso,
    che è esattamente ciò che non serve prevedere.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT min(e.id)         AS event_id,
                   g.id              AS cell_id,
                   g.aoi_id,
                   min(e.event_time) AS event_time,
                   ST_X(ST_Centroid(g.geom)) AS lon,
                   ST_Y(ST_Centroid(g.geom)) AS lat,
                   ST_Centroid(g.geom) AS geom
            FROM flood_events e
            JOIN grid_cells g ON ST_Intersects(g.geom, e.geom)
            WHERE e.event_time >= $1
            GROUP BY g.id, g.aoi_id, g.geom
            ORDER BY min(e.event_time)
            """,
            min_occurrence,
        )
    return [
        _PositiveEvent(
            iffi_id=str(r["event_id"]),
            cell_id=str(r["cell_id"]),
            aoi_id=str(r["aoi_id"]),
            occurrence_date=r["event_time"],
            centroid_lonlat=(float(r["lon"]), float(r["lat"])),
            geom=r["geom"],
        )
        for r in rows
    ]


async def _load_wildfire_positives(
    *, min_occurrence: datetime, max_occurrence: datetime | None = None
) -> list[_PositiveEvent]:
    """Giorni-incendio da `fire_events` (#66), uno per cella-giorno.

    Ogni giorno di fuoco è un positivo a sé e non un evento per cella: un
    incendio che brucia tre giorni è tre giornate in cui quella cella era in
    pericolo, ed è la stessa scelta che `fire_events` ha già fatto.

    Il timestamp è **mezzogiorno UTC**, non mezzanotte: il FWI di Van Wagner è
    definito sulle condizioni di mezzogiorno locale, e ancorare i campioni a
    mezzanotte chiederebbe alla catena l'indice del giorno sbagliato al
    confine.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT e.cell_id, e.event_date, g.aoi_id,
                   ST_X(ST_Centroid(g.geom)) AS lon,
                   ST_Y(ST_Centroid(g.geom)) AS lat,
                   ST_Centroid(g.geom) AS geom
            FROM fire_events e
            JOIN grid_cells g ON g.id = e.cell_id
            WHERE e.event_date >= $1::date
              AND ($2::date IS NULL OR e.event_date <= $2::date)
            ORDER BY e.event_date, e.cell_id
            """,
            min_occurrence.date(),
            max_occurrence.date() if max_occurrence else None,
        )
    return [
        _PositiveEvent(
            iffi_id=f"{r['cell_id']}@{r['event_date'].isoformat()}",
            cell_id=str(r["cell_id"]),
            aoi_id=str(r["aoi_id"]),
            occurrence_date=datetime.combine(r["event_date"], time(12, 0), tzinfo=UTC),
            centroid_lonlat=(float(r["lon"]), float(r["lat"])),
            geom=r["geom"],
        )
        for r in rows
    ]


async def _wildfire_background(
    *,
    positives: list[_PositiveEvent],
    target: int,
    rng: random.Random,
    window: tuple[datetime, datetime],
) -> list[tuple[str, str, float, float, datetime]]:
    """Pseudo-assenze caso-controllo per l'incendio.

    **FIRMS è presence-only**, quindi l'assenza di un evento non prova che non
    sia bruciato: nuvole, chioma e roghi sotto la soglia di rilevamento non
    compaiono. Le negative si campionano, non si leggono.

    Due popolazioni in parti uguali, e servono a cose diverse:

    * **la stessa cella in un giorno senza fuoco** — insegna il *quando*: la
      cella è identica in tutto tranne il meteo, quindi la differenza che il
      modello impara è la finestra meteorologica;
    * **una cella mai bruciata, in un giorno qualsiasi della finestra** —
      insegna il *dove*: combustibile, pendenza e memoria del fuoco.
    Con le sole prime, un modello che dicesse "qui brucia sempre" avrebbe
    ragione su metà del dataset; con le sole seconde, il meteo non conterebbe.
    """
    lo, hi = window
    span_days = max(1, (hi - lo).days)
    fire_days: dict[str, set[date]] = {}
    for ev in positives:
        fire_days.setdefault(ev.cell_id, set()).add(ev.occurrence_date.date())

    same_cell_target = target // 2
    out: list[tuple[str, str, float, float, datetime]] = []
    burnt = list(positives)
    rng.shuffle(burnt)
    attempts = 0
    while len(out) < same_cell_target and burnt and attempts < same_cell_target * 20:
        attempts += 1
        ev = burnt[attempts % len(burnt)]
        day = (lo + timedelta(days=rng.randrange(span_days))).date()
        if day in fire_days.get(ev.cell_id, set()):
            continue
        out.append(
            (
                ev.cell_id,
                ev.aoi_id,
                ev.centroid_lonlat[0],
                ev.centroid_lonlat[1],
                datetime.combine(day, time(12, 0), tzinfo=UTC),
            )
        )

    never_burnt = await _never_burnt_pool(exclude_cells=set(fire_days))
    rng.shuffle(never_burnt)
    for cell_id, aoi_id, lon, lat in never_burnt[: target - len(out)]:
        day = (lo + timedelta(days=rng.randrange(span_days))).date()
        out.append((cell_id, aoi_id, lon, lat, datetime.combine(day, time(12, 0), tzinfo=UTC)))
    return out


async def _never_burnt_pool(*, exclude_cells: set[str]) -> list[tuple[str, str, float, float]]:
    """Celle senza alcun giorno-incendio registrato.

    `fire_density = 0` e non "assente da `fire_events`": la colonna è già il
    conteggio dei giorni-incendio e sta sulla stessa riga delle altre feature,
    quindi il filtro è un indice invece di un anti-join su 224.000 righe.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT g.id, g.aoi_id,
                   ST_X(ST_Centroid(g.geom)) AS lon,
                   ST_Y(ST_Centroid(g.geom)) AS lat
            FROM grid_cells g
            JOIN cell_static_factors c ON c.cell_id = g.id
            WHERE c.fire_density = 0
            ORDER BY g.id
            """
        )
    return [
        (str(r["id"]), str(r["aoi_id"]), float(r["lon"]), float(r["lat"]))
        for r in rows
        if str(r["id"]) not in exclude_cells
    ]


async def _load_background_pool(*, exclude_cells: set[str]) -> list[tuple[str, str, float, float]]:
    """Return ``[(cell_id, aoi_id, lon, lat), ...]`` for sampling."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, aoi_id,
                   ST_X(ST_Centroid(geom)) AS lon,
                   ST_Y(ST_Centroid(geom)) AS lat
            FROM grid_cells
            ORDER BY id
            """
        )
    return [
        (str(r["id"]), str(r["aoi_id"]), float(r["lon"]), float(r["lat"]))
        for r in rows
        if str(r["id"]) not in exclude_cells
    ]


async def _build_flood_features(cell_id: str, valuation_time: datetime) -> dict[str, Any]:  # noqa: ARG001
    """Vettore statico per il pericolo alluvione (#64).

    Non il vettore delle frane con un nome diverso: la suscettibilità
    idraulica, il suolo sigillato e la posizione topografica sono i predittori
    dell'allagamento, mentre densità IFFI e velocità InSAR descrivono un
    versante che si muove — infilarle qui darebbe al challenger delle colonne
    che non parlano del suo fenomeno.

    Manca la parte dinamica, come per le frane: pioggia e portata storiche
    richiedono un replay offline, che è quello che fa `limen backtest-flood`.
    """
    static = await cell_static_factors_repo.get_for_cell(cell_id)
    if static is None:
        return {"static": {}}
    # Accesso diretto e non `getattr(..., None)`: un campo che la riga non
    # porta deve essere un errore di tipo, non un None silenzioso. Con
    # `getattr` il vettore usciva senza `imperviousness_norm` su tutti i
    # 14.124 campioni e sembrava soltanto un dato mancante.
    return {
        "static": {
            "flood_hazard_norm": _maybe_float(static.flood_hazard_norm),
            "imperviousness_norm": _maybe_float(static.imperviousness_norm),
            "elevation_m": _maybe_float(static.elevation_m),
            "slope_deg": _maybe_float(static.slope_deg),
            "twi": _maybe_float(static.twi),
            "distance_to_road_m": _maybe_float(static.distance_to_road_m),
        },
    }


async def _fire_days_before(cell_id: str, *, before: datetime) -> int:
    """Giorni-incendio della cella **strettamente prima** di una data.

    Non `cell_static_factors.fire_density`, che conta tutta l'era VIIRS —
    compreso il giorno etichettato. Misurato: con la densità completa lo SHAP
    dava a quella feature un'importanza media di 3,32 contro 0,29 del FWI,
    cioè il modello leggeva in gran parte la propria etichetta. È leakage
    temporale, e non si riporta: si toglie.
    """
    async with acquire() as conn:
        value = await conn.fetchval(
            "SELECT count(*)::int FROM fire_events WHERE cell_id = $1 AND event_date < $2",
            cell_id,
            before.date(),
        )
    return int(value or 0)


async def _build_wildfire_features(cell_id: str, valuation_time: datetime) -> dict[str, Any]:
    """Vettore statico dell'incendio (#68).

    Combustibile, morfologia, interfaccia urbano-foresta e memoria del fuoco.
    Il combustibile passa per la **stessa** `fuel.for_code` del motore V1: se
    il challenger leggesse la mappa CLC in modo suo, batterebbe la V1 anche
    solo per aver letto il combustibile diversamente, e non sapremmo quale
    delle due cose ha vinto.

    La parte dinamica (FWI, ISI, DC del giorno) la riempie
    :mod:`limen.ml.fire_features`, che ricostruisce la catena: è ricorsiva e
    non si legge da una tabella statica.
    """
    static = await cell_static_factors_repo.get_for_cell(cell_id)
    if static is None:
        return {"fire": {}}
    thresholds = load_hazard_thresholds(HazardType.WILDFIRE)
    assert isinstance(thresholds, WildfireThresholds)
    return {
        "fire": {
            "fuel_class_norm": thresholds.fuel.for_code(static.landuse_code),
            "wui_proximity_norm": _maybe_float(static.wui_proximity_norm),
            # Solo il passato del campione: vedi `_fire_days_before`.
            "density_hist": float(await _fire_days_before(cell_id, before=valuation_time)),
            # Input grezzo, non feature: serve a rigiocare la baseline V1 sullo
            # stesso campione. Se il challenger e il campione leggessero la
            # mappa CLC in due modi diversi, una vittoria non direbbe quale
            # delle due cose ha vinto. `_flatten` lo ignora perché non è un
            # numero.
            "landuse_code": static.landuse_code,
        },
        "static": {"slope_deg": _maybe_float(static.slope_deg)},
    }


async def _build_features(cell_id: str, valuation_time: datetime) -> dict[str, Any]:  # noqa: ARG001
    """Pull the static + InSAR + exposure feature vector for one cell.

    Meteo / seismic / fire are dynamic and would need an offline replay
    against historical archives. V2 starts with the static + InSAR
    surface (the strongest leakage-safe baseline); subsequent training
    passes will splice in cached ERA5 windows via ``DistributedCache``.
    """
    static = await cell_static_factors_repo.get_for_cell(cell_id)
    insar = await cell_insar_features_repo.get_for_cell(cell_id)
    features: dict[str, Any] = {
        "static": {
            "susc_ispra": _maybe_float(getattr(static, "susc_ispra", None)),
            "iffi_density_500": _maybe_float(getattr(static, "iffi_density_500", None)),
            "distance_to_iffi_m": _maybe_float(getattr(static, "distance_to_iffi_m", None)),
            "slope_deg": _maybe_float(getattr(static, "slope_deg", None)),
            "twi": _maybe_float(getattr(static, "twi", None)),
            "curvature": _maybe_float(getattr(static, "curvature", None)),
            "litho_weight": _maybe_float(getattr(static, "litho_weight", None)),
            "pai_class_norm": _maybe_float(getattr(static, "pai_class_norm", None)),
        },
        "insar": {
            "velocity_mmy": insar.insar_velocity_mmy if insar is not None else None,
            "accel_mmy2": insar.insar_accel_mmy2 if insar is not None else None,
            "scatterer_count": insar.scatterer_count if insar is not None else 0,
        },
    }
    return features


def _maybe_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def wildfire_features_to_bundle(
    *, cell_id: str, aoi_id: str, valuation_time: datetime, features: dict[str, Any]
) -> CellFeatureBundle | None:
    """Ricostruisce il bundle incendio da un vettore memorizzato (#68).

    Serve alla **baseline FWI-only**: il gate di promozione confronta il
    challenger con il motore V1 sulla stessa partizione, e per farlo la V1
    deve poter dare un punteggio allo stesso campione.

    Ritorna ``None`` quando la parte meteo manca: senza FWI il motore V1
    darebbe zero, e zero non è "nessun pericolo misurato" ma "nessun
    pericolo", quindi la baseline sembrerebbe brava per aver dichiarato
    sicuri i giorni che non abbiamo arricchito.
    """
    fire = dict(features.get("fire") or {})
    if "fwi" not in fire:
        return None
    static_dict = dict(features.get("static") or {})
    # `wui_proximity_norm` **non** entra nel bundle: il motore incendio non la
    # legge, serve alla priorità degli alert. Resta una feature del
    # challenger, che può usare più informazione della V1 — è il punto di un
    # challenger — purché la V1 riceva esattamente i suoi input.
    static = StaticFactors(
        cell_id=cell_id,
        slope_deg=static_dict.get("slope_deg"),
        landuse_code=fire.get("landuse_code"),
    )
    return CellFeatureBundle(
        aoi_id=aoi_id,
        cell_id=cell_id,
        static=static,
        dynamic=DynamicInputs(
            valuation_time=valuation_time,
            fire_weather=FireWeatherState(
                day=valuation_time.date(),
                # FFMC/DMC/BUI non sono nel vettore: il motore incendio legge
                # `fwi` per il punteggio e gli altri codici servono alla
                # ricorsione, che qui è già stata percorsa. Si passano i
                # neutri dello schema invece di inventare valori.
                ffmc=0.0,
                dmc=0.0,
                dc=float(fire.get("dc") or 0.0),
                isi=float(fire.get("isi") or 0.0),
                bui=0.0,
                fwi=float(fire["fwi"]),
                chain_days=int(fire.get("chain_days") or 0),
            ),
        ),
    )


def features_to_bundle(
    *, cell_id: str, aoi_id: str, valuation_time: datetime, features: dict[str, Any]
) -> CellFeatureBundle:
    """Reconstruct a :class:`CellFeatureBundle` from a stored feature dict.

    Used by tests to prove train/serve parity: the V1 deterministic
    engine MUST be able to score the same bundle the ML model trained
    on. Missing fields degrade gracefully to ``None``.
    """
    static_dict = dict(features.get("static") or {})
    static = StaticFactors(
        cell_id=cell_id, **{k: v for k, v in static_dict.items() if v is not None}
    )
    # Rebuild an hourly rainfall series from the stored antecedent aggregates
    # so the V1 baseline scores the same water the ML trains on (fair
    # champion/challenger comparison): last 24 h at rain_24h's mean rate, the
    # 24-72 h tail at its own mean rate. api_30 flows straight through.
    rain = dict(features.get("rain") or {})
    samples: list[RainfallSample] = []
    r24 = float(rain.get("rain_24h_mm") or 0.0)
    r72 = float(rain.get("rain_72h_mm") or 0.0)
    tail = max(0.0, r72 - r24)
    for i in range(72):
        rate = (r24 / 24.0) if i < 24 else (tail / 48.0)
        if rate > 0:
            samples.append(
                RainfallSample(
                    timestamp=valuation_time - timedelta(hours=i + 1), precipitation_mm=rate
                )
            )
    api_30 = rain.get("rain_30d_mm")
    return CellFeatureBundle(
        aoi_id=aoi_id,
        cell_id=cell_id,
        static=static,
        dynamic=DynamicInputs(
            valuation_time=valuation_time,
            rainfall=RainfallSeries(samples=tuple(samples)),
            api_30_mm=float(api_30) if api_30 is not None else None,
        ),
    )


#: Sorgente dell'etichetta e costruttore del vettore, per pericolo. Una
#: tabella invece di una catena di ternari: al terzo pericolo la catena era
#: già illeggibile, e questa dice a colpo d'occhio cosa cambia fra i tre.
_LABEL_SOURCE_BY_HAZARD: dict[HazardType, LabelSource] = {
    HazardType.LANDSLIDE: "italica",
    HazardType.FLOOD: "copernicus-ems",
    HazardType.WILDFIRE: "firms",
}

_FEATURE_BUILDER_BY_HAZARD: dict[
    HazardType, Callable[[str, datetime], Awaitable[dict[str, Any]]]
] = {
    HazardType.LANDSLIDE: _build_features,
    HazardType.FLOOD: _build_flood_features,
    HazardType.WILDFIRE: _build_wildfire_features,
}


async def extract_training_samples(
    *,
    settings: Settings | None = None,
    min_occurrence: datetime | None = None,
    max_occurrence: datetime | None = None,
    dataset_version_id: int | None = None,
    rng_seed: int | None = None,
    hazard: HazardType = DEFAULT_HAZARD,
) -> int:
    """Extract positive + background samples and persist them.

    Returns the total number of rows written. Idempotent —
    :func:`training_samples_repo.insert_many` upserts on
    ``(cell_id, hazard_type, valuation_time, label_source)``.

    ``hazard`` scelge catalogo **e** vettore di feature insieme, perché le due
    cose non sono separabili: le etichette dell'alluvione sono i perimetri
    osservati di Copernicus EMS e i suoi predittori sono idraulici, quelle
    delle frane sono i punti e-ITALICA con predittori di versante, e quelle
    dell'incendio sono i giorni-incendio FIRMS con predittori di combustibile.

    ``max_occurrence`` esiste per l'incendio (#68): la catena FWI va
    ricostruita giorno per giorno dall'archivio meteo, quindi la finestra di
    addestramento è limitata da quanto se ne può ricostruire — e va dichiarata
    invece di estrarre positivi che nessun enricher riuscirà a completare.
    """
    s = settings or get_settings()
    seed = rng_seed if rng_seed is not None else s.training.seed
    rng = random.Random(seed)
    grid = SpatialBlockGrid(edge_deg=s.training.spatial_block_deg)
    cutoff = min_occurrence or datetime(2000, 1, 1, tzinfo=UTC)

    label_source: LabelSource = _LABEL_SOURCE_BY_HAZARD.get(hazard, "italica")
    build = _FEATURE_BUILDER_BY_HAZARD.get(hazard, _build_features)

    if hazard is HazardType.WILDFIRE:
        positives = await _load_wildfire_positives(
            min_occurrence=cutoff, max_occurrence=max_occurrence
        )
    elif hazard is HazardType.FLOOD:
        positives = await _load_flood_positives(min_occurrence=cutoff)
    else:
        positives = await _load_positives(min_occurrence=cutoff)
    if not positives:
        _log.warning(
            "training.no_positives",
            hazard=hazard.value,
            min_occurrence=cutoff.isoformat(),
        )
        return 0

    positive_samples: list[TrainingSample] = []
    seen_pos: set[tuple[str, datetime]] = set()
    for ev in positives:
        key = (ev.cell_id, ev.occurrence_date)
        if key in seen_pos:
            continue
        seen_pos.add(key)
        features = await build(ev.cell_id, ev.occurrence_date)
        block = grid.block_for(*ev.centroid_lonlat)
        positive_samples.append(
            TrainingSample(
                cell_id=ev.cell_id,
                valuation_time=ev.occurrence_date,
                label=1,
                label_source=label_source,
                features=features,
                split_block=block,
                dataset_version_id=dataset_version_id,
                hazard_type=hazard,
            )
        )

    target_background = int(len(positive_samples) * s.training.background_ratio)
    background_samples: list[TrainingSample] = []

    if hazard is HazardType.WILDFIRE:
        # Le negative dell'incendio portano un **tempo**, non una data
        # pseudo-casuale per cella: il predittore dominante è il meteo del
        # giorno, quindi una negativa senza un giorno credibile non
        # insegnerebbe nulla. Finestra = quella dei positivi.
        window = (
            min(ev.occurrence_date for ev in positives),
            max(ev.occurrence_date for ev in positives),
        )
        controls = await _wildfire_background(
            positives=positives, target=target_background, rng=rng, window=window
        )
        for cell_id, _aoi_id, lon, lat, valuation_time in controls:
            features = await build(cell_id, valuation_time)
            background_samples.append(
                TrainingSample(
                    cell_id=cell_id,
                    valuation_time=valuation_time,
                    label=0,
                    label_source="background",
                    features=features,
                    split_block=grid.block_for(lon, lat),
                    dataset_version_id=dataset_version_id,
                    hazard_type=hazard,
                )
            )
    else:
        pool = await _load_background_pool(exclude_cells={ev.cell_id for ev in positives})
        rng.shuffle(pool)
        for cell_id, _aoi_id, lon, lat in pool[:target_background]:
            # Stable pseudo-time per cell so re-runs don't shuffle the dataset.
            seed_bytes = hashlib.sha256(cell_id.encode("utf-8")).digest()
            offset_days = int.from_bytes(seed_bytes[:4], "big") % (365 * 10)
            valuation_time = cutoff + timedelta(days=offset_days)
            features = await build(cell_id, valuation_time)
            block = grid.block_for(lon, lat)
            background_samples.append(
                TrainingSample(
                    cell_id=cell_id,
                    valuation_time=valuation_time,
                    label=0,
                    label_source="background",
                    features=features,
                    split_block=block,
                    dataset_version_id=dataset_version_id,
                    hazard_type=hazard,
                )
            )

    written = await training_samples_repo.insert_many(positive_samples + background_samples)
    _log.info(
        "training.extract.done",
        hazard=hazard.value,
        positives=len(positive_samples),
        background=len(background_samples),
        rows_written=written,
        blocks=len({s.split_block for s in positive_samples + background_samples}),
    )
    return written


def spatial_block_folds(blocks: list[str], k: int, *, rng_seed: int = 42) -> list[list[str]]:
    """Partition ``blocks`` into ``k`` disjoint groups for CV.

    Round-robin assignment after a deterministic shuffle — guarantees
    every fold contains a mix of geographic regions while keeping
    spatial autocorrelation between folds at zero (no leakage).
    """
    if k < 2:
        raise ValueError("k must be >= 2")
    if not blocks:
        return [[] for _ in range(k)]
    ordered = sorted(set(blocks))
    rng = random.Random(rng_seed)
    rng.shuffle(ordered)
    folds: list[list[str]] = [[] for _ in range(k)]
    for i, block in enumerate(ordered):
        folds[i % k].append(block)
    return folds


__all__ = [
    "LabelSource",
    "SpatialBlockGrid",
    "extract_training_samples",
    "features_to_bundle",
    "spatial_block_folds",
]
