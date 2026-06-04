"""Geological zonal stats — lithology dominance + fault distance."""

from __future__ import annotations

from shapely.geometry import LineString, Polygon

from limen.integrations.geological.litho_weights import (
    DEFAULT_LITHO_WEIGHT,
    LITHO_WEIGHTS,
    normalise_litho,
)
from limen.integrations.geological.zonal import (
    DISTANCE_CAP_M,
    LithologyPolygon,
    _haversine_m,
    compute_geological_stats,
)


# ---------------------------------------------------------------------------
# normalise_litho
# ---------------------------------------------------------------------------
def test_normalise_picks_argille_for_marnose_clays() -> None:
    key, w = normalise_litho("Argille marnose")
    assert key == "argille"
    assert w == LITHO_WEIGHTS["argille"]


def test_normalise_is_case_and_whitespace_tolerant() -> None:
    a = normalise_litho("  CALCARI  ")
    b = normalise_litho("calcari")
    assert a == b


def test_normalise_unknown_returns_neutral_weight() -> None:
    key, w = normalise_litho("rare exotic stone")
    assert key == "unknown"
    assert w == DEFAULT_LITHO_WEIGHT


def test_normalise_none_returns_unknown() -> None:
    key, w = normalise_litho(None)
    assert key == "unknown"
    assert w == DEFAULT_LITHO_WEIGHT


def test_litho_weights_are_in_unit_interval() -> None:
    assert all(0.0 <= w <= 1.0 for w in LITHO_WEIGHTS.values())


# ---------------------------------------------------------------------------
# compute_geological_stats — dominance + fault distance
# ---------------------------------------------------------------------------
def _square(lon: float, lat: float, side: float = 0.05) -> Polygon:
    return Polygon(
        [
            (lon, lat),
            (lon + side, lat),
            (lon + side, lat + side),
            (lon, lat + side),
            (lon, lat),
        ]
    )


def test_dominant_lithology_by_intersection_area() -> None:
    """Cell overlaps two lithology polygons; the larger overlap wins."""
    cell = _square(16.80, 41.10, side=0.10)
    # Argille polygon covers most of the cell.
    argille = _square(16.78, 41.08, side=0.12)
    calcari = _square(16.85, 41.10, side=0.04)
    stats = compute_geological_stats(
        cells={"c-1": cell},
        lithology_polygons=[
            LithologyPolygon(geom=argille, label="Argille scagliose"),
            LithologyPolygon(geom=calcari, label="Calcari massicci"),
        ],
    )
    assert len(stats) == 1
    assert stats[0].lithology == "Argille scagliose"
    assert stats[0].litho_weight == LITHO_WEIGHTS["argille"]


def test_no_overlap_returns_none_lithology() -> None:
    cell = _square(0.0, 0.0)
    far_polygon = _square(50.0, 50.0)
    stats = compute_geological_stats(
        cells={"c-far": cell},
        lithology_polygons=[
            LithologyPolygon(geom=far_polygon, label="Argille"),
        ],
    )
    assert stats[0].lithology is None
    assert stats[0].litho_weight is None


def test_fault_distance_is_zero_when_fault_crosses_cell() -> None:
    cell = _square(16.80, 41.10, side=0.10)
    # Line crossing the cell centre.
    crossing_fault = LineString([(16.78, 41.15), (16.92, 41.15)])
    stats = compute_geological_stats(
        cells={"c-1": cell},
        lithology_polygons=[],
        faults=[crossing_fault],
    )
    assert stats[0].dist_faults_m is not None
    # The centroid of the cell is at ~(16.85, 41.15), and the fault passes
    # through that latitude — distance should be near zero.
    assert stats[0].dist_faults_m < 100.0


def test_fault_distance_uses_nearest_when_multiple_faults() -> None:
    cell = _square(16.80, 41.10, side=0.10)
    near_fault = LineString([(16.86, 41.20), (16.88, 41.20)])  # ~5 km north
    far_fault = LineString([(17.50, 42.00), (17.52, 42.00)])  # ~120 km away
    stats = compute_geological_stats(
        cells={"c-1": cell},
        lithology_polygons=[],
        faults=[near_fault, far_fault],
    )
    # Centroid at (~16.85, ~41.15); nearest fault at ~lat 41.20 → ~5 km north.
    # The cap at 50 km is more lax; the near fault must win.
    assert stats[0].dist_faults_m is not None
    assert stats[0].dist_faults_m < 20_000.0


def test_haversine_known_distance_approx() -> None:
    """Sanity: lat 41 → 41.1 ≈ 11.1 km (1° of latitude ≈ 111 km)."""
    d = _haversine_m(16.85, 41.10, 16.85, 41.20)
    assert 10_500 < d < 11_500


def test_fault_cap_returned_when_no_faults_in_search_buffer() -> None:
    """Faults exist but none within the ~50 km query buffer.

    The function caps distance reporting at ``DISTANCE_CAP_M`` so the
    breakdown column never overflows the engine's normalisation range.
    """
    cell = _square(16.80, 41.10, side=0.05)
    far_fault = LineString([(30.0, 60.0), (30.5, 60.5)])  # nowhere near
    stats = compute_geological_stats(
        cells={"c-1": cell},
        lithology_polygons=[],
        faults=[far_fault],
    )
    assert stats[0].dist_faults_m == DISTANCE_CAP_M
