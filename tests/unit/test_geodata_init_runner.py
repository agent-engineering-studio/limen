"""Geo-Data Service — init runner filter + dry-run behaviour."""

from __future__ import annotations

from pathlib import Path

import pytest

from geodata.init.runner import _filter_specs, run_init_pipeline
from geodata.manifest import load_manifest


def _shipped() -> Path:
    return Path(__file__).resolve().parents[2] / "geodata" / "src" / "geodata" / "datasets.yaml"


# ---------------------------------------------------------------------------
# _filter_specs
# ---------------------------------------------------------------------------
def test_filter_keeps_only_enabled_by_default() -> None:
    manifest = load_manifest(_shipped())
    out = _filter_specs(manifest.datasets, only=None, region=None)
    names = {d.name for d in out}
    assert "pai_frane" in names
    # idraulica is shipped disabled.
    assert "idraulica" not in names


def test_filter_only_restricts_to_named_datasets() -> None:
    manifest = load_manifest(_shipped())
    out = _filter_specs(manifest.datasets, only="pai_frane,iffi_puglia_piff_poly", region=None)
    assert {d.name for d in out} == {"pai_frane", "iffi_puglia_piff_poly"}


def test_filter_only_handles_whitespace_separators() -> None:
    manifest = load_manifest(_shipped())
    out = _filter_specs(manifest.datasets, only=" pai_frane ,  ", region=None)
    assert {d.name for d in out} == {"pai_frane"}


def test_filter_region_is_case_insensitive() -> None:
    manifest = load_manifest(_shipped())
    out = _filter_specs(manifest.datasets, only=None, region="PUGLIA")
    assert all(d.region == "puglia" for d in out)
    assert len(out) > 0


def test_filter_region_combined_with_only() -> None:
    manifest = load_manifest(_shipped())
    out = _filter_specs(
        manifest.datasets,
        only="iffi_basilicata_aree_poly,iffi_puglia_aree_poly",
        region="basilicata",
    )
    assert {d.name for d in out} == {"iffi_basilicata_aree_poly"}


def test_filter_returns_empty_when_no_match() -> None:
    manifest = load_manifest(_shipped())
    assert _filter_specs(manifest.datasets, only=None, region="emilia-romagna") == ()


# ---------------------------------------------------------------------------
# run_init_pipeline — dry-run path doesn't hit the network
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_dry_run_returns_zero_without_network(tmp_path: Path) -> None:
    rc = await run_init_pipeline(
        manifest_path=_shipped(),
        only="pai_frane",
        dry_run=True,
    )
    assert rc == 0


@pytest.mark.asyncio
async def test_no_matching_dataset_returns_zero() -> None:
    rc = await run_init_pipeline(
        manifest_path=_shipped(),
        only="not-a-real-dataset",
    )
    assert rc == 0
