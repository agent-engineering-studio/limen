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
