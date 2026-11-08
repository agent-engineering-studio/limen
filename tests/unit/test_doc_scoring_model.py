"""I pesi di S scritti in docs/scoring-model.md sono quelli di landslide.yaml (#493)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from limen.core.scoring.regional_thresholds import load_regional_thresholds

DOC = Path(__file__).resolve().parents[2] / "docs" / "scoring-model.md"
RIGA_PESO = re.compile(r"^\|\s*`(\w+)`\s*\|\s*([0-9]+(?:\.[0-9]+)?)\s*\|")


def _pesi_statici_del_documento() -> dict[str, float]:
    testo = DOC.read_text(encoding="utf-8")
    sezione = testo.split("### S — componente statica", 1)[1].split("\n### ", 1)[0]
    pesi: dict[str, float] = {}
    for riga in sezione.splitlines():
        trovata = RIGA_PESO.match(riga.strip())
        if trovata:
            pesi[trovata.group(1)] = float(trovata.group(2))
    return pesi


def test_pesi_di_s_nel_documento_uguali_allo_yaml() -> None:
    attesi = load_regional_thresholds().static.weights.model_dump()
    scritti = _pesi_statici_del_documento()
    assert scritti.keys() == attesi.keys()
    for chiave, valore in attesi.items():
        assert scritti[chiave] == pytest.approx(valore), chiave
