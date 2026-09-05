"""Regional-thresholds YAML loader: validation + override semantics."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from limen.core.scoring.regional_thresholds import (
    DEFAULT_THRESHOLDS_PATH,
    RegionalThresholds,
    load_regional_thresholds,
)


def test_default_yaml_loads() -> None:
    t = load_regional_thresholds()
    assert isinstance(t, RegionalThresholds)
    assert t.model_version
    assert (
        t.weights.static
        + t.weights.meteo
        + t.weights.seismic
        + t.weights.fire
        + t.weights.hydrology
        == pytest.approx(1.0)
    )


def _load_default_dict() -> dict[str, object]:
    return dict(yaml.safe_load(DEFAULT_THRESHOLDS_PATH.read_text(encoding="utf-8")))


def _write(tmp_path: Path, cfg: dict[str, object]) -> Path:
    out = tmp_path / "rt.yaml"
    out.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return out


def test_weights_must_sum_to_one(tmp_path: Path) -> None:
    cfg = _load_default_dict()
    cfg["weights"]["static"] = 0.5  # type: ignore[index]
    with pytest.raises(ValidationError, match=r"weights must sum to 1\.0"):
        load_regional_thresholds(_write(tmp_path, cfg))


def test_caine_macroregions_must_contain_default(tmp_path: Path) -> None:
    cfg = _load_default_dict()
    cfg["caine"]["macroregions"] = {"southern_italy": {"alpha": 8.6, "beta": 0.44}}  # type: ignore[index]
    with pytest.raises(ValidationError, match="italy_default"):
        load_regional_thresholds(_write(tmp_path, cfg))


def test_class_cutoffs_must_cover_unit(tmp_path: Path) -> None:
    cfg = _load_default_dict()
    cfg["classes"]["very_high"] = [0.75, 0.99]  # type: ignore[index]
    with pytest.raises(ValidationError, match="cover \\[0, 1\\]"):
        load_regional_thresholds(_write(tmp_path, cfg))


def test_class_cutoffs_must_be_contiguous(tmp_path: Path) -> None:
    cfg = _load_default_dict()
    cfg["classes"]["high"] = [0.55, 0.70]  # type: ignore[index]
    cfg["classes"]["very_high"] = [0.75, 1.00]  # type: ignore[index]
    with pytest.raises(ValidationError, match="contiguous"):
        load_regional_thresholds(_write(tmp_path, cfg))


def test_override_path_bypasses_cache(tmp_path: Path) -> None:
    """Loading an override path doesn't return the cached default object."""
    cfg = _load_default_dict()
    cfg["model_version"] = "test-override"
    override = load_regional_thresholds(_write(tmp_path, cfg))
    default = load_regional_thresholds()
    assert override.model_version == "test-override"
    assert default.model_version != "test-override"


def test_packaged_path_points_at_the_hazard_file() -> None:
    """Il file di configurazione vive per pericolo (issue #84): il default
    è quello delle frane, e la risoluzione via importlib.resources deve
    funzionare in qualunque layout di installazione."""
    from limen.core.models.hazard import DEFAULT_HAZARD, HazardType
    from limen.core.scoring.regional_thresholds import hazard_thresholds_path

    assert DEFAULT_THRESHOLDS_PATH.name == "landslide.yaml"
    assert DEFAULT_THRESHOLDS_PATH.parent.name == "hazards"
    assert hazard_thresholds_path(DEFAULT_HAZARD) == DEFAULT_THRESHOLDS_PATH
    assert hazard_thresholds_path(HazardType.FLOOD).name == "flood.yaml"


def test_hazard_without_a_file_fails_instead_of_borrowing_landslide() -> None:
    """Un pericolo senza YAML non deve silenziosamente ereditare le soglie
    delle frane: sarebbero numeri sbagliati presentati come giusti."""
    from limen.core.models.hazard import HazardType
    from limen.core.scoring.regional_thresholds import load_hazard_thresholds

    # `flood` è l'unico pericolo dell'enum ancora senza YAML (#63).
    with pytest.raises(FileNotFoundError):
        load_hazard_thresholds(HazardType.FLOOD)
