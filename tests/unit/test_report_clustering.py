from limen.core.models.risk import RiskLevel
from limen.report.clustering import ClusterRow, _levels_at_least, group_into_clusters

_CELL_A = '{"type":"Polygon","coordinates":[[[16,41],[16.01,41],[16.01,41.01],[16,41.01],[16,41]]]}'
_CELL_B = '{"type":"Polygon","coordinates":[[[16.1,41.1],[16.11,41.1],[16.11,41.11],[16.1,41.11],[16.1,41.1]]]}'  # noqa: E501


def _row(
    cid: str,
    cluster: int,
    score: float,
    level: str,
    geom_json: str | None = None,
) -> ClusterRow:
    return ClusterRow(
        cluster_id=cluster,
        cell_id=cid,
        aoi_id="puglia",
        score=score,
        level=level,
        s=0.5,
        m=0.1,
        e=0.0,
        f=0.0,
        h=0.0,
        lon=16.0,
        lat=41.0,
        geom_json=geom_json or _CELL_A,
    )


def test_rows_group_by_cluster_id_and_rank_by_max_score() -> None:
    rows = [
        _row("a", 0, 0.6, "High"),
        _row("b", 0, 0.9, "VeryHigh"),
        _row("c", 1, 0.7, "High"),
    ]
    clusters = group_into_clusters(rows)
    assert len(clusters) == 2
    assert clusters[0].max_score == 0.9
    assert clusters[0].cell_ids == ["b", "a"]
    assert clusters[0].dominant.cell_id == "b"
    assert clusters[1].cell_ids == ["c"]


def test_bbox_is_union_of_member_cells() -> None:
    clusters = group_into_clusters(
        [
            _row("a", 0, 0.9, "VeryHigh"),
            _row("b", 0, 0.6, "High", geom_json=_CELL_B),
        ]
    )
    minx, miny, maxx, maxy = clusters[0].bbox
    assert minx == 16.0 and miny == 41.0
    assert maxx == 16.11 and maxy == 41.11


def test_cluster_and_member_ordering_is_deterministic_on_ties() -> None:
    # Two clusters with equal max_score → ordered by smallest cell_id first.
    rows = [
        _row("z", 0, 0.8, "VeryHigh"),
        _row("a", 1, 0.8, "VeryHigh"),
    ]
    clusters = group_into_clusters(rows)
    assert [c.cell_ids[0] for c in clusters] == ["a", "z"]

    # Two members with equal score → ordered by cell_id.
    same = group_into_clusters(
        [
            _row("y", 0, 0.7, "High"),
            _row("x", 0, 0.7, "High"),
        ]
    )
    assert same[0].cell_ids == ["x", "y"]


def test_levels_at_least() -> None:
    assert _levels_at_least(RiskLevel.High) == ["High", "VeryHigh"]
    assert _levels_at_least(RiskLevel.None_) == [
        "None",
        "Low",
        "Moderate",
        "High",
        "VeryHigh",
    ]
