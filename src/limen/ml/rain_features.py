"""Offline rain-feature enrichment for training samples (CERRA replay).

Each training sample is a (cell, timestamp) pair; the ML model needs the
antecedent rainfall the cell saw at that moment. We snap each cell to a
0.1° node, group samples by calendar date (same 30-day window) and batch up
to 100 nodes per CERRA archive call — the same machinery the backtest uses.

Idempotent: only samples whose ``features`` lack the ``rain`` block are
fetched; re-runs resume where they left off.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from limen.core.logging import get_logger
from limen.data.db import acquire
from limen.integrations.openmeteo.client import OpenMeteoHttpClient
from limen.integrations.openmeteo.grid import build_rain_nodes, nearest_node

log = get_logger(__name__)

_NODE_DEG = 0.1
_WINDOW_DAYS = 30
# CERRA coverage ends in 2021; samples beyond it keep an empty rain block
# (flagged, not silently zeroed).
_CERRA_MAX = datetime(2021, 12, 31, tzinfo=UTC)


def compute_rain_aggregates(
    samples: list[tuple[datetime, float]], as_of: datetime
) -> dict[str, float]:
    """Antecedent aggregates from an hourly (timestamp, mm) series."""
    h24 = as_of - timedelta(hours=24)
    h72 = as_of - timedelta(hours=72)
    d30 = as_of - timedelta(days=_WINDOW_DAYS)
    rain_24 = rain_72 = rain_30d = 0.0
    max_i24 = 0.0
    for ts, mm in samples:
        if ts > as_of or ts < d30:
            continue
        rain_30d += mm
        if ts >= h72:
            rain_72 += mm
        if ts >= h24:
            rain_24 += mm
            max_i24 = max(max_i24, mm)
    return {
        "rain_24h_mm": round(rain_24, 2),
        "rain_72h_mm": round(rain_72, 2),
        "rain_30d_mm": round(rain_30d, 2),
        "max_i_24h_mmh": round(max_i24, 2),
    }


async def _pending(conn: Any) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT t.id, t.cell_id, t.valuation_time,
               ST_X(ST_Centroid(g.geom)) AS lon, ST_Y(ST_Centroid(g.geom)) AS lat
        FROM training_samples t
        JOIN grid_cells g ON g.id = t.cell_id
        WHERE NOT (t.features ? 'rain')
        ORDER BY t.valuation_time
        """
    )
    return [dict(r) for r in rows]


async def enrich_rain_features(*, batch_pause_s: float = 0.15) -> int:
    """Fill ``features.rain`` for every sample that lacks it. Returns count."""
    client = OpenMeteoHttpClient()
    async with acquire() as conn:
        pending = await _pending(conn)
    if not pending:
        log.info("rain_enrich.nothing_to_do")
        return 0

    # Italy-wide node lattice so node identity is stable across batches.
    lattice = build_rain_nodes((6.6, 35.4, 18.6, 47.2), spacing=_NODE_DEG)

    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    skipped_out_of_range = 0
    for s in pending:
        t = s["valuation_time"]
        if t > _CERRA_MAX:
            skipped_out_of_range += 1
            continue
        s["node"] = nearest_node(float(s["lon"]), float(s["lat"]), lattice)
        by_day[t.date().isoformat()].append(s)

    log.info(
        "rain_enrich.start",
        pending=len(pending),
        day_groups=len(by_day),
        out_of_cerra_range=skipped_out_of_range,
    )

    done = 0
    for day, group in sorted(by_day.items()):
        as_of_day = datetime.fromisoformat(day).replace(tzinfo=UTC)
        nodes = sorted({s["node"] for s in group})
        coords = [lattice[n] for n in nodes]
        grid = await client.get_rainfall_grid(
            nodes=coords,
            window_start=as_of_day - timedelta(days=_WINDOW_DAYS),
            window_end=as_of_day + timedelta(days=1),
            use_archive=True,
            model="cerra",
        )
        series_by_node = {
            n: [(w.timestamp, w.precipitation_mm) for w in series]
            for n, series in zip(nodes, grid, strict=False)
        }
        async with acquire() as conn, conn.transaction():
            for s in group:
                series = series_by_node.get(s["node"], [])
                rain = compute_rain_aggregates(series, s["valuation_time"])
                if not series:
                    rain["degraded"] = 1.0
                await conn.execute(
                    """
                    UPDATE training_samples
                    SET features = features || jsonb_build_object('rain', $2::jsonb)
                    WHERE id = $1
                    """,
                    s["id"],
                    json.dumps(rain),
                )
                done += 1
        if done % 2000 < len(group):
            log.info("rain_enrich.progress", done=done, total=len(pending))
        await asyncio.sleep(batch_pause_s)

    log.info("rain_enrich.done", enriched=done, out_of_cerra_range=skipped_out_of_range)
    return done
