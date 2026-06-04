"""Geo-Data Service — manifest schema + datasets.yaml integrity."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from geodata.manifest import (
    ALLOWED_URL_PREFIX,
    DatasetFormat,
    DatasetManifest,
    DatasetSpec,
    load_manifest,
)


# ---------------------------------------------------------------------------
# DatasetSpec — per-entry validation
# ---------------------------------------------------------------------------
def _good_spec(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "pai_frane",
        "url": ALLOWED_URL_PREFIX + "opendata/wms/foo.zip",
        "format": "shapefile-zip",
        "target": "pai_landslide_hazard",
        "enabled": True,
    }
    base.update(overrides)
    return base


def test_dataset_spec_accepts_minimal_entry() -> None:
    spec = DatasetSpec.model_validate(_good_spec())
    assert spec.name == "pai_frane"
    assert spec.format is DatasetFormat.SHAPEFILE_ZIP


def test_dataset_spec_rejects_extra_fields() -> None:
    with pytest.raises(ValueError):
        DatasetSpec.model_validate(_good_spec(stowaway="oops"))


def test_dataset_spec_rejects_unofficial_url() -> None:
    with pytest.raises(ValueError, match="must start with"):
        DatasetSpec.model_validate(_good_spec(url="https://evil.example/foo.zip"))


@pytest.mark.parametrize(
    "bad_name",
    [
        "Mixed_Case",
        "with-dash",
        "12_leading_digit",
        "with space",
        "",
    ],
)
def test_dataset_spec_rejects_bad_name(bad_name: str) -> None:
    with pytest.raises(ValueError):
        DatasetSpec.model_validate(_good_spec(name=bad_name))


# ---------------------------------------------------------------------------
# DatasetManifest — top-level shape
# ---------------------------------------------------------------------------
def test_manifest_rejects_duplicate_names() -> None:
    raw = {
        "version": "test",
        "datasets": [
            _good_spec(name="iffi_x"),
            _good_spec(name="iffi_x"),
        ],
    }
    with pytest.raises(ValueError, match="duplicate dataset name"):
        DatasetManifest.model_validate(raw)


def test_manifest_filters_enabled() -> None:
    manifest = DatasetManifest.model_validate(
        {
            "version": "test",
            "datasets": [
                _good_spec(name="enabled_one", enabled=True),
                _good_spec(name="disabled_one", enabled=False),
            ],
        }
    )
    enabled = manifest.enabled_datasets()
    assert len(enabled) == 1
    assert enabled[0].name == "enabled_one"


def test_manifest_by_region() -> None:
    manifest = DatasetManifest.model_validate(
        {
            "version": "test",
            "datasets": [
                _good_spec(name="iffi_puglia_a", region="puglia"),
                _good_spec(name="iffi_basilicata_a", region="basilicata"),
            ],
        }
    )
    assert {d.name for d in manifest.by_region("Puglia")} == {"iffi_puglia_a"}
    assert {d.name for d in manifest.by_region("basilicata")} == {"iffi_basilicata_a"}


# ---------------------------------------------------------------------------
# Shipped datasets.yaml — must round-trip through the loader
# ---------------------------------------------------------------------------
def _shipped_manifest_path() -> Path:
    return Path(__file__).resolve().parents[2] / "geodata" / "src" / "geodata" / "datasets.yaml"


def test_shipped_manifest_loads() -> None:
    path = _shipped_manifest_path()
    assert path.exists(), f"expected packaged manifest at {path}"
    manifest = load_manifest(path)
    # The pilot region datasets must be present and enabled.
    enabled = {d.name for d in manifest.enabled_datasets()}
    assert "pai_frane" in enabled
    assert "iffi_puglia_piff_poly" in enabled
    assert "iffi_basilicata_piff_poly" in enabled
    # Dizionari JSONs must be enabled (the MCP iffi_query decodes via them).
    assert "iffi_dizionari_cause" in enabled
    # Phase 12+: idraulica is now enabled — feeds the engine's H component.
    assert "idraulica" in enabled


def test_shipped_manifest_every_url_is_official() -> None:
    path = _shipped_manifest_path()
    raw = yaml.safe_load(path.read_text())
    for entry in raw["datasets"]:
        assert entry["url"].startswith(ALLOWED_URL_PREFIX), entry


def test_shipped_manifest_load_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_manifest(tmp_path / "missing.yaml")
