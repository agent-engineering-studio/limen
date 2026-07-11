"""Cluster di celle contigue High+ via PostGIS ST_ClusterDBSCAN.

La query gira su mv_latest_risk (geom + factors + livello già insieme).
Il raggruppamento in Cluster è puro e testabile senza DB.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from limen.core.logging import get_logger
from limen.core.models.risk import RiskLevel
from limen.data.db import acquire

log = get_logger(__name__)

# minpoints := 1: ogni cella High+ deve finire in un cluster — nessun filtro
# noise/orphan. Per un report anche una cella isolata forma la sua zona.
_CLUSTER_SQL = """
SELECT ST_ClusterDBSCAN(centroid, eps := $2, minpoints := 1) OVER () AS cluster_id,
       cell_id, aoi_id, risk_score AS score, risk_level AS level,
       factors,
       ST_X(centroid) AS lon, ST_Y(centroid) AS lat,
       ST_AsGeoJSON(geom) AS geom_json
FROM   mv_latest_risk
WHERE  aoi_id = $1 AND risk_level = ANY($3::text[])
"""


@dataclass(frozen=True)
class ClusterRow:
    cluster_id: int
    cell_id: str
    aoi_id: str
    score: float
    level: str
    s: float
    m: float
    e: float
    f: float
    h: float
    lon: float
    lat: float
    geom_json: str


@dataclass(frozen=True)
class Cluster:
    cluster_id: int
    aoi_id: str
    cell_ids: list[str]
    rows: list[ClusterRow]
    max_score: float
    dominant: ClusterRow
    bbox: tuple[float, float, float, float]  # minx, miny, maxx, maxy


def _bbox_of(rows: list[ClusterRow]) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for r in rows:
        coords = json.loads(r.geom_json)["coordinates"]
        for x, y in coords[0]:
            xs.append(x)
            ys.append(y)
    return (min(xs), min(ys), max(xs), max(ys))


def group_into_clusters(rows: list[ClusterRow]) -> list[Cluster]:
    by_id: dict[int, list[ClusterRow]] = {}
    for r in rows:
        by_id.setdefault(r.cluster_id, []).append(r)
    clusters: list[Cluster] = []
    for cid, members in by_id.items():
        members_sorted = sorted(members, key=lambda r: (-r.score, r.cell_id))
        clusters.append(
            Cluster(
                cluster_id=cid,
                aoi_id=members_sorted[0].aoi_id,
                cell_ids=[r.cell_id for r in members_sorted],
                rows=members_sorted,
                max_score=members_sorted[0].score,
                dominant=members_sorted[0],
                bbox=_bbox_of(members_sorted),
            )
        )
    return sorted(clusters, key=lambda c: (-c.max_score, c.cell_ids[0]))


def _levels_at_least(minimum: RiskLevel) -> list[str]:
    order = [
        RiskLevel.None_,
        RiskLevel.Low,
        RiskLevel.Moderate,
        RiskLevel.High,
        RiskLevel.VeryHigh,
    ]
    idx = order.index(minimum)
    return [lv.value for lv in order[idx:]]


# ponytail: dup of _coerce_json in api/endpoints/risk.py; 5 trivial lines, not
# worth a shared module + endpoint refactor. Consolidate into a data-layer
# helper if a third caller appears.
def _coerce_json(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    return dict(json.loads(value))


async def load_clusters(aoi_id: str, *, eps_deg: float, min_level: RiskLevel) -> list[Cluster]:
    async with acquire() as conn:
        records = await conn.fetch(_CLUSTER_SQL, aoi_id, eps_deg, _levels_at_least(min_level))
    rows = []
    for r in records:
        factors = _coerce_json(r["factors"])
        rows.append(
            ClusterRow(
                cluster_id=int(r["cluster_id"]),
                cell_id=str(r["cell_id"]),
                aoi_id=str(r["aoi_id"]),
                score=float(r["score"]),
                level=str(r["level"]),
                s=float(factors.get("s", 0.0)),
                m=float(factors.get("m", 0.0)),
                e=float(factors.get("e", 0.0)),
                f=float(factors.get("f", 0.0)),
                h=float(factors.get("h", 0.0)),
                lon=float(r["lon"]),
                lat=float(r["lat"]),
                geom_json=str(r["geom_json"]),
            )
        )
    clusters = group_into_clusters(rows)
    log.info(
        "report.clustering.loaded",
        aoi_id=aoi_id,
        rows=len(rows),
        clusters=len(clusters),
    )
    return clusters
