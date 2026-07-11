import json

from limen.report.clustering import Cluster, ClusterRow
from limen.report.geojson import coord_label, zone_center, zone_feature_collection_json

_GEOM = '{"type":"Polygon","coordinates":[[[16.0,41.0],[16.1,41.0],[16.1,41.1],[16.0,41.1],[16.0,41.0]]]}'  # noqa: E501


def _row(cell_id: str, level: str, score: float) -> ClusterRow:
    return ClusterRow(
        cluster_id=0,
        cell_id=cell_id,
        aoi_id="it-puglia",
        score=score,
        level=level,
        s=0.5,
        m=0.1,
        e=0.0,
        f=0.0,
        h=0.0,
        lon=16.05,
        lat=41.05,
        geom_json=_GEOM,
    )


def _cluster() -> Cluster:
    rows = [_row("a", "High", 0.6), _row("b", "VeryHigh", 0.9)]
    return Cluster(
        cluster_id=0,
        aoi_id="it-puglia",
        cell_ids=["b", "a"],
        rows=rows,
        max_score=0.9,
        dominant=rows[1],
        bbox=(16.0, 41.0, 16.1, 41.1),
    )


def test_feature_collection_has_one_feature_per_cell_with_colour() -> None:
    raw = zone_feature_collection_json(_cluster())
    fc = json.loads(raw)
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 2
    props = fc["features"][0]["properties"]
    assert props["color"].startswith("#")
    assert props["cell_id"] == "a"


def test_feature_collection_escapes_angle_bracket_for_script_embed() -> None:
    # embeddable in <script type="application/json"> without a stray </script>
    assert "<" not in zone_feature_collection_json(_cluster())


def test_zone_center_is_bbox_midpoint() -> None:
    lat, lon = zone_center(_cluster())
    assert lat == 41.05
    assert lon == 16.05


def test_coord_label_hemispheres() -> None:
    assert coord_label(41.05, 16.05) == "41.0500° N, 16.0500° E"
    assert coord_label(-1.5, -2.5) == "1.5000° S, 2.5000° W"
