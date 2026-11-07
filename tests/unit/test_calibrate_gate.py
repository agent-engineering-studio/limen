"""Il cancello S↔ISPRA nel log di `limen calibrate`: spento, non misurato, esito."""

from __future__ import annotations

from pathlib import Path

from limen.cli.calibrate import _AoiCalibration, _gate


def _cal(correlation: float | None, ok: bool) -> _AoiCalibration:
    return _AoiCalibration("it-puglia", 10, correlation, ok, 0, Path("x.md"))


def test_con_la_soglia_a_null_il_cancello_e_spento() -> None:
    assert _gate(_cal(None, True), None) == "off"


def test_zero_righe_di_suscettibilita_non_e_superato() -> None:
    assert _gate(_cal(None, False), 0.3) == "non misurato"


def test_con_la_correlazione_si_legge_l_esito() -> None:
    assert _gate(_cal(0.5, True), 0.3) == "pass"
    assert _gate(_cal(0.1, False), 0.3) == "fail"
