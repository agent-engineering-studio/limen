"""Per-zone GeoJSON + geographic coordinates for the interactive mini-maps.

Replaces the old raster/SVG snapshot: the cell polygons ship as GeoJSON and a
client-side Leaflet map (see the template) renders them over a real basemap
with zoom/pan. No server-side image rendering, no Pillow.
"""

from __future__ import annotations

import json

from limen.core.models.risk import RiskLevel
from limen.report.clustering import Cluster
from limen.report.palette import color_for


def zone_feature_collection_json(cluster: Cluster) -> str:
    """Script-safe GeoJSON string of the zone's cells (each with its hex colour).

    ``<`` is escaped to ``\\u003c`` so the JSON can be embedded verbatim in a
    ``<script type="application/json">`` block without a stray ``</script>``
    ever terminating it early. Marked ``|safe`` in the template.
    """
    features = [
        {
            "type": "Feature",
            "geometry": json.loads(r.geom_json),
            "properties": {
                "level": r.level,
                "color": color_for(RiskLevel(r.level)),
                "cell_id": r.cell_id,
                "score": round(r.score, 3),
            },
        }
        for r in cluster.rows
    ]
    fc = {"type": "FeatureCollection", "features": features}
    return json.dumps(fc, ensure_ascii=False).replace("<", "\\u003c")


def zone_center(cluster: Cluster) -> tuple[float, float]:
    """(lat, lon) centre of the zone's bounding box."""
    minx, miny, maxx, maxy = cluster.bbox
    return ((miny + maxy) / 2.0, (minx + maxx) / 2.0)


def coord_label(lat: float, lon: float) -> str:
    """Human-facing coordinates, e.g. ``41.2345° N, 16.5678° E``."""
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return f"{abs(lat):.4f}° {ns}, {abs(lon):.4f}° {ew}"
