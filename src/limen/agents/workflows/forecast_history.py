"""Persist per-cell forecast scores for the trend chart (issue #41).

Sweeps each AOI at +24/+48/+72 h and writes the **≥ Moderate** cells to
``risk_assessments`` with ``horizon="+Hh"`` and ``pipeline_version=
"v1-forecast+Hh"`` (``computed_at=now()`` → the UI derives the target time as
``computed_at + H``), and keeps the **current** forecast in ``latest_forecast``.

The history is append-only, like every partitioned table here: retention drops
partitions, it never deletes rows. Readers that want "the forecast now" read
``latest_forecast``; the history is for replaying how a forecast evolved.
"""

from __future__ import annotations

import json
from typing import Any

from limen.agents.workflows.forecast import run_forecast
from limen.config.settings import Settings, get_settings
from limen.core.logging import get_logger
from limen.core.models.context import CellRiskRecord
from limen.core.models.hazard import DEFAULT_HAZARD, HazardType
from limen.core.models.risk import RiskLevel
from limen.data.db import acquire

log = get_logger(__name__)

# Persist only cells at/above this level — those shown in the list / report.
_LEVEL_ORDER = (
    RiskLevel.None_,
    RiskLevel.Low,
    RiskLevel.Moderate,
    RiskLevel.High,
    RiskLevel.VeryHigh,
)
_DEFAULT_FLOOR = RiskLevel.Moderate
_DEFAULT_HORIZONS = (24, 48, 72)

_INSERT_SQL = """
INSERT INTO risk_assessments (
    cell_id, computed_at, hazard_type, horizon, score, class, factors,
    explanation, pipeline_version, dataset_versions
) VALUES ($1, now(), $2, $3, $4, $5, $6::jsonb, '{}'::jsonb, $7, ARRAY[]::bigint[])
"""


#: Lo stato corrente della previsione (migrazione 057). Si cancellano **tutte**
#: le celle valutate da questa corsa, non solo quelle che tornano sopra
#: soglia: una cella scesa sotto Moderato deve perdere la riga, altrimenti
#: resterebbe lì a dire la previsione di ieri.
_LATEST_DELETE_SQL = """
DELETE FROM latest_forecast
WHERE hazard_type = $1 AND horizon_h = $2 AND cell_id = ANY($3::text[])
"""

_LATEST_UPSERT_SQL = """
INSERT INTO latest_forecast (cell_id, hazard_type, horizon_h, score, class, run_at, target_at)
SELECT u.cell_id, $1::hazard_type, $2, u.score, u.class, now(),
       now() + make_interval(hours => $2)
FROM unnest($3::text[], $4::float8[], $5::text[]) AS u(cell_id, score, class)
ON CONFLICT (cell_id, hazard_type, horizon_h) DO UPDATE
SET score = EXCLUDED.score, class = EXCLUDED.class,
    run_at = EXCLUDED.run_at, target_at = EXCLUDED.target_at
"""


#: La previsione per comune, per ogni pericolo e a ogni livello (059).
_COMUNE_DELETE_SQL = """
DELETE FROM latest_forecast_comune
WHERE hazard_type = $1 AND horizon_h = $2 AND istat_code = ANY($3::text[])
"""

_COMUNE_INSERT_SQL = """
INSERT INTO latest_forecast_comune
    (istat_code, hazard_type, horizon_h, score, class, rain_mm, run_at, target_at)
SELECT u.istat_code, $1::hazard_type, $2, u.score, u.class, u.rain_mm, now(),
       now() + make_interval(hours => $2)
FROM unnest($3::text[], $4::float8[], $5::text[], $6::float8[])
     AS u(istat_code, score, class, rain_mm)
"""


def per_comune(
    cell_results: list[CellRiskRecord], comune_of: dict[str, str]
) -> dict[str, tuple[float, str, float | None]]:
    """Pure: per comune, il punteggio più alto, la sua classe e la pioggia.

    Tutte le celle, non solo quelle sopra soglia: è il punto della tabella.
    La pioggia c'è solo per l'alluvione — è il suo breakdown a portarla — e
    per gli altri pericoli resta ``None``.
    """
    from limen.core.models.risk import FloodBreakdown

    out: dict[str, tuple[float, str, float | None]] = {}
    for c in cell_results:
        istat = comune_of.get(c.cell_id)
        if istat is None:
            continue
        pioggia = c.breakdown.rain_mm if isinstance(c.breakdown, FloodBreakdown) else None
        corrente = out.get(istat)
        if corrente is None:
            out[istat] = (float(c.score), c.level.value, pioggia)
            continue
        punteggio, classe, p = corrente
        if float(c.score) > punteggio:
            punteggio, classe = float(c.score), c.level.value
        if pioggia is not None:
            p = pioggia if p is None else max(p, pioggia)
        out[istat] = (punteggio, classe, p)
    return out


def at_or_above(level: RiskLevel, floor: RiskLevel) -> bool:
    return _LEVEL_ORDER.index(level) >= _LEVEL_ORDER.index(floor)


def cells_to_persist(
    cell_results: list[CellRiskRecord], *, floor: RiskLevel = _DEFAULT_FLOOR
) -> list[CellRiskRecord]:
    """Pure: the cells worth persisting for the forecast trend (≥ floor)."""
    return [c for c in cell_results if at_or_above(c.level, floor)]


async def persist_forecast_run(
    conn: Any,
    horizon_h: int,
    cell_results: list[CellRiskRecord],
    *,
    floor: RiskLevel = _DEFAULT_FLOOR,
    hazard: HazardType = DEFAULT_HAZARD,
) -> int:
    """Write the ≥floor cells of one forecast run.

    Lo storico è **solo in append**, come ogni altra tabella partizionata del
    progetto: la retention la fa `drop_expired_partitions()`, mai un DELETE.
    Prima qui c'era un DELETE delle righe previsionali precedenti per
    `cell_id`, senza filtro sulla data, quindi attraverso tutte le partizioni:
    su questo disco superava il timeout del comando già su Basilicata (8.000
    celle), e la previsione d'incendio si fermava lì. Serviva a tenere
    nello storico una sola corsa per cella; ora lo stato corrente è
    `latest_forecast`, e i lettori leggono quello.
    """
    keep = cells_to_persist(cell_results, floor=floor)
    horizon = f"+{horizon_h}h"
    pipeline_version = f"v1-forecast+{horizon_h}h"
    cell_ids = [c.cell_id for c in keep]
    async with conn.transaction():
        for c in keep:
            factors = c.breakdown.factors_payload()
            await conn.execute(
                _INSERT_SQL,
                c.cell_id,
                hazard.value,
                horizon,
                c.score,
                c.level.value,
                json.dumps(factors, default=str),
                pipeline_version,
            )
        await conn.execute(
            _LATEST_DELETE_SQL,
            hazard.value,
            horizon_h,
            [c.cell_id for c in cell_results],
        )
        await conn.execute(
            _LATEST_UPSERT_SQL,
            hazard.value,
            horizon_h,
            cell_ids,
            [float(c.score) for c in keep],
            [c.level.value for c in keep],
        )
        righe = await conn.fetch(
            "SELECT cell_id, istat_code FROM cell_comune WHERE cell_id = ANY($1::text[])",
            [c.cell_id for c in cell_results],
        )
        comuni = per_comune(cell_results, {str(r["cell_id"]): str(r["istat_code"]) for r in righe})
        if comuni:
            codici = list(comuni)
            await conn.execute(_COMUNE_DELETE_SQL, hazard.value, horizon_h, codici)
            await conn.execute(
                _COMUNE_INSERT_SQL,
                hazard.value,
                horizon_h,
                codici,
                [comuni[k][0] for k in codici],
                [comuni[k][1] for k in codici],
                [comuni[k][2] for k in codici],
            )
    return len(keep)


async def run_forecast_history(
    *,
    aoi_ids: list[str] | None = None,
    horizons: tuple[int, ...] = _DEFAULT_HORIZONS,
    settings: Settings | None = None,
    hazard: HazardType = DEFAULT_HAZARD,
) -> int:
    """Sweep all AOIs at the given horizons and persist ≥Moderate forecast cells."""
    settings = settings or get_settings()
    floor = _DEFAULT_FLOOR
    if aoi_ids is None:
        async with acquire() as conn:
            rows = await conn.fetch("SELECT id FROM aoi ORDER BY id")
        aoi_ids = [str(r["id"]) for r in rows]

    total = 0
    for aoi_id in aoi_ids:
        for h in horizons:
            run = await run_forecast(aoi_id=aoi_id, horizon_h=h, settings=settings, hazard=hazard)
            async with acquire() as conn:
                n = await persist_forecast_run(
                    conn, h, run.cell_results, floor=floor, hazard=hazard
                )
            total += n
            log.info(
                "forecast_history.persisted",
                aoi_id=aoi_id,
                hazard=hazard.value,
                horizon_h=h,
                cells=n,
            )
    log.info(
        "forecast_history.done",
        hazard=hazard.value,
        aois=len(aoi_ids),
        horizons=list(horizons),
        cells=total,
    )
    await _registra_corsa(hazard, total)
    return total


#: Dove si registra che la corsa di un pericolo è avvenuta, anche a zero celle.
LAST_RUN_KEY = "forecast:last_run:{hazard}"


async def _registra_corsa(hazard: HazardType, celle: int) -> None:
    """Segna che la previsione di `hazard` è girata, **anche a zero celle**.

    Lo stato previsionale tiene solo le celle da Moderato in su. Dedurre da
    lì se una corsa è avvenuta confonde due risposte opposte: una giornata
    asciutta, in cui l'alluvione è prevista sotto soglia ovunque e non lascia
    righe, e una corsa mai fatta. Misurato il 30 settembre: l'Abruzzo a +24 h
    ha dato zero celle, e la testata avrebbe detto «previsione non
    disponibile» di un pericolo appena calcolato.

    Tre giorni di scadenza: una previsione più vecchia non è più quella di
    stanotte, e mostrarla come disponibile sarebbe peggio che tacere.
    """
    from datetime import UTC, datetime

    from limen.data.caching.postgres_cache import PostgresCache

    try:
        await PostgresCache().set_json(
            LAST_RUN_KEY.format(hazard=hazard.value),
            {"run_at": datetime.now(UTC).isoformat(), "cells": celle},
            ttl_seconds=3 * 24 * 3600,
        )
    except Exception as exc:
        log.warning("forecast_history.last_run.failed", hazard=hazard.value, error=str(exc))
