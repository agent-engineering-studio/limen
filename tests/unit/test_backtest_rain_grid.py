"""Unit tests for the shared rainfall-node grid helpers (pure)."""

from __future__ import annotations

from limen.integrations.openmeteo.grid import build_rain_nodes, nearest_node


def test_build_rain_nodes_covers_bbox() -> None:
    bbox = (16.0, 40.0, 16.5, 40.5)
    nodes = build_rain_nodes(bbox, spacing=0.25)
    # 0.0, 0.25, 0.5 along each axis inclusive → 3 x 3.
    assert len(nodes) == 9
    assert (16.0, 40.0) in nodes
    assert any(abs(lon - 16.5) < 1e-9 and abs(lat - 40.5) < 1e-9 for lon, lat in nodes)


def test_build_rain_nodes_degenerate_bbox_falls_back_to_centroid() -> None:
    # A zero-area bbox still yields exactly one node (its centre).
    nodes = build_rain_nodes((16.0, 40.0, 16.0, 40.0), spacing=0.25)
    assert nodes == [(16.0, 40.0)]


def test_nearest_node_picks_closest() -> None:
    nodes = [(16.0, 40.0), (16.5, 40.0), (16.0, 40.5)]
    assert nearest_node(16.05, 40.02, nodes) == 0
    assert nearest_node(16.48, 40.03, nodes) == 1
    assert nearest_node(16.02, 40.47, nodes) == 2
