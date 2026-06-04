"""V2.2 — DL meteo serving wrapper graceful-degradation behaviour."""

from __future__ import annotations

from pathlib import Path

import pytest

from limen.ml.dl.model import SEQUENCE_LENGTH_HOURS
from limen.ml.dl.serve import DLMeteoProbability, _pad_or_trim


def test_returns_neutral_when_model_missing(tmp_path: Path) -> None:
    """No file on disk → 0.5 neutral, no crash."""
    serve = DLMeteoProbability(tmp_path / "nonexistent.onnx")
    assert serve.predict([0.0] * SEQUENCE_LENGTH_HOURS) == pytest.approx(0.5)


def test_pad_or_trim_pads_short_window() -> None:
    out = _pad_or_trim([1.0, 2.0], length=5)
    assert out == [0.0, 0.0, 0.0, 1.0, 2.0]


def test_pad_or_trim_trims_long_window() -> None:
    out = _pad_or_trim([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], length=4)
    assert out == [3.0, 4.0, 5.0, 6.0]


def test_pad_or_trim_passthrough() -> None:
    window = [float(i) for i in range(5)]
    assert _pad_or_trim(window, length=5) == window


def test_sequence_length_constant() -> None:
    assert SEQUENCE_LENGTH_HOURS == 168


def test_serve_exposes_model_path(tmp_path: Path) -> None:
    p = tmp_path / "rainfall_cnn.onnx"
    serve = DLMeteoProbability(p)
    assert serve.model_path == p
    assert serve.sequence_length == SEQUENCE_LENGTH_HOURS
