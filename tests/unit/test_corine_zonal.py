"""CORINE majority-class logic — pure tests on synthetic arrays."""

from __future__ import annotations

import numpy as np

from limen.integrations.corine.zonal import _majority_class


def test_majority_picks_most_frequent_class() -> None:
    arr = np.array([[111, 112, 112, 311], [112, 311, 511, 112]])
    code, n = _majority_class(arr, nodata=None)
    assert code == "112"  # appears 4 times
    assert n == 8


def test_majority_breaks_ties_by_smallest_code() -> None:
    arr = np.array([[1, 2, 3, 1, 2, 3]])  # each appears twice
    code, n = _majority_class(arr, nodata=None)
    assert code == "1"
    assert n == 6


def test_majority_excludes_nodata_value() -> None:
    arr = np.array([[-1, -1, 111, 111, 311]], dtype=np.int16)
    code, n = _majority_class(arr, nodata=-1)
    assert code == "111"
    assert n == 3


def test_majority_excludes_nan_for_float_arrays() -> None:
    arr = np.array([[np.nan, 211.0, 211.0, np.nan]], dtype=np.float32)
    code, n = _majority_class(arr, nodata=None)
    assert code == "211"
    assert n == 2


def test_majority_empty_returns_none() -> None:
    code, n = _majority_class(np.array([], dtype=np.int16), nodata=None)
    assert code is None
    assert n == 0


def test_majority_all_nodata_returns_none() -> None:
    code, n = _majority_class(np.array([[-1, -1, -1]], dtype=np.int16), nodata=-1)
    assert code is None
    assert n == 0


# --- riproiezione costruita una volta per ciclo ------------------------------


def test_geom_reprojector_matches_a_per_geometry_reprojection() -> None:
    """Il ciclo veloce deve dare gli stessi numeri di quello lento.

    ``Transformer.from_crs`` costava 67 ms per cella (misurato: 5,9 ore su
    312.550 celle, contro 5 minuti costruendolo fuori dal ciclo). Il
    trasformatore è però lo stesso per ogni cella, quindi spostarlo fuori è
    solo lavoro risparmiato: questo test è ciò che lo dimostra invece di
    lasciarlo alla fiducia.
    """
    from pyproj import Transformer
    from shapely.geometry import box
    from shapely.ops import transform as shp_transform

    from limen.integrations.dem.zonal import geom_reprojector

    celle = [box(16.0 + i * 0.01, 41.0, 16.01 + i * 0.01, 41.01) for i in range(5)]
    riusato = geom_reprojector(src_crs=4326, dst_crs=3035)
    for g in celle:
        uno = shp_transform(Transformer.from_crs(4326, 3035, always_xy=True).transform, g)
        assert riusato(g).equals_exact(uno, tolerance=1e-9)


def test_geom_reprojector_is_the_identity_when_the_crs_matches() -> None:
    from shapely.geometry import box

    from limen.integrations.dem.zonal import geom_reprojector

    g = box(16.0, 41.0, 16.01, 41.01)
    assert geom_reprojector(src_crs=4326, dst_crs=4326)(g) is g
