"""Geological zonal stats — lithology dominance + fault distance."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from shapely.geometry import LineString, Polygon

from limen.core.scoring.regional_thresholds import LithologyWeights, load_regional_thresholds
from limen.integrations.geological.litho_weights import litho_weight_for
from limen.integrations.geological.zonal import (
    DISTANCE_CAP_M,
    LithologyPolygon,
    _haversine_m,
    compute_geological_stats,
)

# ---------------------------------------------------------------------------
# litho_weight_for: la tabella sta in landslide.yaml (#471)
# ---------------------------------------------------------------------------
_PESI = load_regional_thresholds().static.lithology


def test_full_label_matches_exactly() -> None:
    assert litho_weight_for("Argille") == 0.85
    assert litho_weight_for("Unita' prevalentemente flyschoidi, torbidi") == 0.80


def test_match_is_case_and_whitespace_tolerant() -> None:
    assert litho_weight_for("  ARGILLE  ") == litho_weight_for("Argille")
    assert litho_weight_for("Marne  e marne\tcalcaree") == 0.70


def test_partial_label_is_not_a_substring_match() -> None:
    assert litho_weight_for("Argille marnose") == _PESI.default


def test_unknown_or_missing_label_takes_yaml_default() -> None:
    assert litho_weight_for("rare exotic stone") == _PESI.default
    assert litho_weight_for(None) == _PESI.default


def test_every_class_of_the_map_is_in_the_yaml() -> None:
    legenda = {
        "Alluvioni e terreni misti",
        "Calcari e dolomie",
        "Unita' prevalentemente flyschoidi, torbidi",
        "Argille",
        "Sabbie e conglomerati",
        "Formazioni prevalentemente arenacee",
        "Lave, piroclastiti ed ignimbriti",
        "Rocce intrusive",
        "Metamorfiti di medio grado",
        "Complessi sedimentari caotici",
        "Marne e marne calcaree",
        "Metamorfiti di vario grado",
        "Metamorfiti di basso grado",
        "Calcari detritici ed organogeni tipo panchina",
        "Depositi glaciali",
        "Laghi e ghiacciai",
        "Ofioliti e pietre verdi",
        "Metamorfiti di alto grado",
        "Gessoso-solfifera, evaporiti",
        "Conglomerati, brecce e depositi clastici",
        "Depositi eolici",
        "Argilloscisti",
        "Travertini",
    }
    assert {k for k in legenda if k.lower() not in _PESI.classes} == set()


def test_weights_are_overridden_by_the_yaml() -> None:
    tabella = LithologyWeights(default=0.1, classes={"Argille": 0.2})
    assert litho_weight_for("argille", tabella) == 0.2
    assert litho_weight_for("Calcari e dolomie", tabella) == 0.1


def test_weight_outside_unit_interval_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LithologyWeights(default=0.5, classes={"Argille": 1.5})


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
            LithologyPolygon(geom=argille, label="Argille"),
            LithologyPolygon(geom=calcari, label="Calcari e dolomie"),
        ],
    )
    assert len(stats) == 1
    assert stats[0].lithology == "Argille"
    assert stats[0].litho_weight == 0.85


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
