"""La soglia degli avvisi sotto «Alto» è del pericolo, nel suo YAML (#477)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from limen.core.models.hazard import HazardType
from limen.core.scoring.regional_thresholds import (
    AlertsBlock,
    hazard_thresholds_path,
    load_hazard_thresholds,
)


@pytest.mark.parametrize("hazard", list(HazardType))
def test_ogni_pericolo_ha_la_sua_soglia(hazard: HazardType) -> None:
    assert 0.0 <= load_hazard_thresholds(hazard).alerts.min_predisposition <= 1.0


@pytest.mark.parametrize("hazard", list(HazardType))
def test_la_soglia_si_cambia_dallo_yaml(hazard: HazardType, tmp_path: Path) -> None:
    raw = yaml.safe_load(hazard_thresholds_path(hazard).read_text(encoding="utf-8"))
    raw["alerts"]["min_predisposition"] = 0.25
    path = tmp_path / f"{hazard.value}.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    assert load_hazard_thresholds(hazard, path).alerts.min_predisposition == 0.25


def test_soglia_fuori_scala_rifiutata() -> None:
    with pytest.raises(ValidationError):
        AlertsBlock(min_predisposition=1.5)
