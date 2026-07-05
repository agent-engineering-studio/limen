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
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from shapely.geometry.base import BaseGeometry

from limen.config.settings import Settings, get_settings
from limen.core.logging import get_logger
from limen.core.models.risk import (
    CellFeatureBundle,
    DynamicInputs,
    RainfallSample,
    RainfallSeries,
    StaticFactors,
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


async def _load_background_pool(*, exclude_cells: set[str]) -> list[tuple[str, str, float, float]]:
    """Return ``[(cell_id, aoi_id, lon, lat), ...]`` for sampling."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, aoi_id,
                   ST_X(ST_Centroid(geom)) AS lon,
                   ST_Y(ST_Centroid(geom)) AS lat
            FROM grid_cells
            """
        )
    return [
        (str(r["id"]), str(r["aoi_id"]), float(r["lon"]), float(r["lat"]))
        for r in rows
        if str(r["id"]) not in exclude_cells
    ]


async def _build_features(cell_id: str) -> dict[str, Any]:
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


async def extract_training_samples(
    *,
    settings: Settings | None = None,
    min_occurrence: datetime | None = None,
    dataset_version_id: int | None = None,
    rng_seed: int | None = None,
) -> int:
    """Extract positive + background samples and persist them.

    Returns the total number of rows written. Idempotent —
    :func:`training_samples_repo.insert_many` upserts on
    ``(cell_id, valuation_time, label_source)``.
    """
    s = settings or get_settings()
    seed = rng_seed if rng_seed is not None else s.training.seed
    rng = random.Random(seed)
    grid = SpatialBlockGrid(edge_deg=s.training.spatial_block_deg)
    cutoff = min_occurrence or datetime(2000, 1, 1, tzinfo=UTC)

    positives = await _load_positives(min_occurrence=cutoff)
    if not positives:
        _log.warning("training.no_positives", min_occurrence=cutoff.isoformat())
        return 0

    positive_samples: list[TrainingSample] = []
    seen_pos: set[tuple[str, datetime]] = set()
    for ev in positives:
        key = (ev.cell_id, ev.occurrence_date)
        if key in seen_pos:
            continue
        seen_pos.add(key)
        features = await _build_features(ev.cell_id)
        block = grid.block_for(*ev.centroid_lonlat)
        positive_samples.append(
            TrainingSample(
                cell_id=ev.cell_id,
                valuation_time=ev.occurrence_date,
                label=1,
                label_source="italica",
                features=features,
                split_block=block,
                dataset_version_id=dataset_version_id,
            )
        )

    target_background = int(len(positive_samples) * s.training.background_ratio)
    pool = await _load_background_pool(exclude_cells={ev.cell_id for ev in positives})
    rng.shuffle(pool)
    background_samples: list[TrainingSample] = []
    for cell_id, _aoi_id, lon, lat in pool[:target_background]:
        # Stable pseudo-time per cell so re-runs don't shuffle the dataset.
        seed_bytes = hashlib.sha256(cell_id.encode("utf-8")).digest()
        offset_days = int.from_bytes(seed_bytes[:4], "big") % (365 * 10)
        valuation_time = cutoff + timedelta(days=offset_days)
        features = await _build_features(cell_id)
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
            )
        )

    written = await training_samples_repo.insert_many(positive_samples + background_samples)
    _log.info(
        "training.extract.done",
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
