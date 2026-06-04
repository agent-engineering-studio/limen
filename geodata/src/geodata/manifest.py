"""Manifest schema for the Geo-Data Service.

``datasets.yaml`` is the single source of truth for what gets
ingested, from where, into which PostGIS table. Adding a dataset =
adding a manifest entry; no code change.

The Pydantic v2 schema is strict (``extra=forbid``) so a typo in the
YAML surfaces immediately, and every URL is checked to start with the
official IdroGEO origin so the init job can never be pointed at a
third-party mirror by accident.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DatasetFormat(StrEnum):
    """Supported source-archive formats.

    The init runner picks an importer per format; see
    :mod:`geodata.init.importers`.
    """

    SHAPEFILE_ZIP = "shapefile-zip"
    GEOJSON_ZIP = "geojson-zip"
    JSON = "json"


# Allowed source prefix. The init runner refuses any URL outside this
# origin so the deployment can never point at a third-party mirror.
ALLOWED_URL_PREFIX = "https://idrogeo.isprambiente.it/"


class DatasetSpec(BaseModel):
    """One manifest entry — a single dataset to ingest."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(..., min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    """Stable internal id used as the natural key in ``dataset_versions``
    and the CLI ``--only`` filter."""

    url: str = Field(..., min_length=1)
    format: DatasetFormat
    target: str = Field(..., min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    """Destination PostGIS table name."""

    region: str | None = None
    """Optional Italian region tag for per-region datasets (e.g. ``puglia``)."""

    enabled: bool = True
    license: str = Field(default="CC-BY-4.0 (ISPRA IdroGEO)")

    # Per-source overrides — most datasets don't need them.
    layer: str | None = None
    """Specific shapefile / GeoJSON layer name to read (when the archive
    contains multiple)."""
    encoding: str | None = None
    """Source-file encoding override (default UTF-8)."""
    srid: int | None = None
    """Source SRID override (default: auto-detect; the importer always
    reprojects to EPSG:4326)."""

    @field_validator("url")
    @classmethod
    def _url_must_be_official(cls, value: str) -> str:
        if not value.startswith(ALLOWED_URL_PREFIX):
            raise ValueError(
                f"manifest URL must start with {ALLOWED_URL_PREFIX!r} (got: {value!r})"
            )
        return value


class DatasetManifest(BaseModel):
    """Top-level manifest — strict, immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str = Field(..., min_length=1)
    """Manifest schema version — bump on incompatible structural change."""
    datasets: tuple[DatasetSpec, ...]

    @model_validator(mode="after")
    def _names_unique(self) -> DatasetManifest:
        seen: set[str] = set()
        for d in self.datasets:
            if d.name in seen:
                raise ValueError(f"duplicate dataset name in manifest: {d.name!r}")
            seen.add(d.name)
        return self

    def enabled_datasets(self) -> tuple[DatasetSpec, ...]:
        return tuple(d for d in self.datasets if d.enabled)

    def by_name(self, name: str) -> DatasetSpec | None:
        for d in self.datasets:
            if d.name == name:
                return d
        return None

    def by_region(self, region: str) -> tuple[DatasetSpec, ...]:
        target = region.strip().lower()
        return tuple(d for d in self.datasets if (d.region or "").lower() == target)


def _load_yaml(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text) or {}


def load_manifest(path: Path | str) -> DatasetManifest:
    """Read + validate the manifest at ``path``.

    Use this everywhere; never instantiate :class:`DatasetManifest`
    directly from arbitrary dicts. The CLI and the importer share this
    loader so any schema drift surfaces at a single point.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"manifest not found: {p}")
    raw = _load_yaml(p)
    return DatasetManifest.model_validate(raw)


__all__ = [
    "ALLOWED_URL_PREFIX",
    "DatasetFormat",
    "DatasetManifest",
    "DatasetSpec",
    "load_manifest",
]
