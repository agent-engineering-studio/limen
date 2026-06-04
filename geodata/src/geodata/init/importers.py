"""Format-specific importers from a local archive into PostGIS.

The runner picks the importer matching the :class:`DatasetFormat`. All
importers share two invariants:

* the destination table is the manifest's ``target`` (DDL lives in
  :mod:`geodata.db`; tables are created on first run),
* every geometry is reprojected to EPSG:4326 + made valid before
  storage.

Heavy I/O deps (``pyogrio``) are imported lazily so the package can
be inspected without them installed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import asyncpg
import structlog

from geodata.manifest import DatasetSpec
from geodata.parsers import (
    PAI_CLASSES,
    normalise_pai_class,
    parse_iffi_attributes,
    parse_pai_attributes,
)

_log: structlog.stdlib.BoundLogger = structlog.get_logger("geodata.init.importers")


@dataclass(frozen=True, slots=True)
class ImportOutcome:
    rows_written: int
    target: str
    notes: str = ""


# ---------------------------------------------------------------------------
# Shapefile import — PAI + IFFI
# ---------------------------------------------------------------------------
def _find_shapefile(extracted: list[Path]) -> Path | None:
    """Pick the first ``.shp`` from the extracted fileset."""
    for p in extracted:
        if p.suffix.lower() == ".shp":
            return p
    return None


def _read_shapefile(path: Path) -> Any:
    """Read with pyogrio; reproject to EPSG:4326."""
    from pyogrio import read_dataframe

    df = read_dataframe(path)
    if df.crs is None:
        df = df.set_crs("EPSG:4326")
    elif df.crs.to_epsg() != 4326:
        df = df.to_crs("EPSG:4326")
    return df


def _row_to_props(row: Any) -> dict[str, Any]:
    """Map a (geo)pandas row into a plain JSON-able dict."""
    out: dict[str, Any] = {}
    for col, val in row.items():
        if col == "geometry":
            continue
        if val is None:
            continue
        out[str(col)] = _coerce_jsonable(val)
    return out


def _coerce_jsonable(value: Any) -> Any:
    # Pandas may surface numpy scalars / Timestamps — coerce to plain
    # Python so json.dumps survives.
    try:
        import numpy as np
        import pandas as pd
    except ImportError:  # pragma: no cover
        return value
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    return value


async def _import_pai_shapefile(
    conn: asyncpg.Connection,
    *,
    spec: DatasetSpec,
    extracted: list[Path],
    dataset_version_id: int | None,
) -> ImportOutcome:
    shp = _find_shapefile(extracted)
    if shp is None:
        raise ValueError(f"{spec.name}: shapefile (.shp) missing from extracted archive")
    df = _read_shapefile(shp)
    rows = 0
    async with conn.transaction():
        if not _is_dataset_locked(spec):
            await conn.execute("DELETE FROM pai_landslide_hazard WHERE dataset_version_id IS NULL")
        for _, geo_row in df.iterrows():
            geom = geo_row.get("geometry")
            if geom is None or not geom.is_valid:
                continue
            attrs = parse_pai_attributes(_row_to_props(geo_row))
            pai_id = attrs["pai_id"]
            if not pai_id:
                continue
            hazard_class = attrs["hazard_class"]
            if hazard_class not in PAI_CLASSES:
                hazard_class = normalise_pai_class(hazard_class)
            payload = json.dumps(attrs["raw"], default=str)
            wkt = geom.wkt
            await conn.execute(
                """
                INSERT INTO pai_landslide_hazard (
                    pai_id, hazard_class, authority, region, geom, attributes,
                    dataset_version_id, updated_at
                ) VALUES (
                    $1, $2, $3, $4,
                    ST_Multi(ST_SetSRID(ST_GeomFromText($5), 4326)),
                    $6::jsonb, $7, now()
                )
                ON CONFLICT (pai_id) DO UPDATE
                SET hazard_class = EXCLUDED.hazard_class,
                    authority    = EXCLUDED.authority,
                    region       = EXCLUDED.region,
                    geom         = EXCLUDED.geom,
                    attributes   = EXCLUDED.attributes,
                    dataset_version_id = EXCLUDED.dataset_version_id,
                    updated_at   = now()
                """,
                pai_id,
                hazard_class,
                attrs["authority"],
                spec.region,
                wkt,
                payload,
                dataset_version_id,
            )
            rows += 1
    return ImportOutcome(rows_written=rows, target=spec.target)


def _is_dataset_locked(spec: DatasetSpec) -> bool:
    """Per-region datasets never wipe each other; national one does."""
    return spec.region is not None


_IFFI_GEOM_TYPE_BY_NAME = {
    "piff_line": "piff_line",
    "piff_poly": "piff_poly",
    "aree_poly": "aree_poly",
    "dgpv_poly": "dgpv_poly",
}


def _infer_iffi_geom_type(spec: DatasetSpec) -> str:
    name = spec.name.lower()
    for marker, value in _IFFI_GEOM_TYPE_BY_NAME.items():
        if name.endswith(marker):
            return value
    return "unknown"


async def _import_iffi_shapefile(
    conn: asyncpg.Connection,
    *,
    spec: DatasetSpec,
    extracted: list[Path],
    dataset_version_id: int | None,
) -> ImportOutcome:
    shp = _find_shapefile(extracted)
    if shp is None:
        raise ValueError(f"{spec.name}: shapefile (.shp) missing from extracted archive")
    if not spec.region:
        raise ValueError(f"{spec.name}: IFFI manifest entries require `region`")
    df = _read_shapefile(shp)
    geom_type = _infer_iffi_geom_type(spec)
    rows = 0
    async with conn.transaction():
        for _, geo_row in df.iterrows():
            geom = geo_row.get("geometry")
            if geom is None or not geom.is_valid:
                continue
            props = _row_to_props(geo_row)
            attrs = parse_iffi_attributes(props)
            iffi_id_raw = attrs["iffi_id"]
            if not iffi_id_raw:
                continue
            composite_id = f"{spec.region}|{iffi_id_raw}|{geom_type}"
            payload = json.dumps(attrs["raw"], default=str)
            wkt = geom.wkt
            await conn.execute(
                """
                INSERT INTO iffi_landslides (
                    id, iffi_id, region, geom_type, movement_type, state,
                    velocity_class, occurrence_date, geom, attributes,
                    dataset_version_id, updated_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8,
                    ST_SetSRID(ST_GeomFromText($9), 4326),
                    $10::jsonb, $11, now()
                )
                ON CONFLICT (id) DO UPDATE
                SET movement_type   = EXCLUDED.movement_type,
                    state           = EXCLUDED.state,
                    velocity_class  = EXCLUDED.velocity_class,
                    occurrence_date = EXCLUDED.occurrence_date,
                    geom            = EXCLUDED.geom,
                    attributes      = EXCLUDED.attributes,
                    dataset_version_id = EXCLUDED.dataset_version_id,
                    updated_at      = now()
                """,
                composite_id,
                iffi_id_raw,
                spec.region,
                geom_type,
                attrs["movement_type"],
                attrs["state"],
                attrs["velocity_class"],
                attrs["occurrence_date"],
                wkt,
                payload,
                dataset_version_id,
            )
            rows += 1
    return ImportOutcome(rows_written=rows, target=spec.target, notes=f"geom_type={geom_type}")


# ---------------------------------------------------------------------------
# JSON import — IFFI Dizionari
# ---------------------------------------------------------------------------
_LOOKUP_TABLES = {
    "iffi_lookup_causes",
    "iffi_lookup_movements",
    "iffi_lookup_lithology",
}


async def _import_dizionario(
    conn: asyncpg.Connection,
    *,
    spec: DatasetSpec,
    json_path: Path,
) -> ImportOutcome:
    if spec.target not in _LOOKUP_TABLES:
        raise ValueError(f"{spec.name}: unrecognised lookup target {spec.target!r}")
    raw_text = json_path.read_text(encoding=spec.encoding or "utf-8")
    payload = json.loads(raw_text)
    pairs = _coerce_dizionario(payload)
    rows = 0
    async with conn.transaction():
        # Replace-all semantics for a tiny lookup table.
        await conn.execute(f"DELETE FROM {spec.target}")
        for code, label in pairs:
            await conn.execute(
                f"INSERT INTO {spec.target} (code, label) VALUES ($1, $2) "
                "ON CONFLICT (code) DO UPDATE SET label = EXCLUDED.label",
                code,
                label,
            )
            rows += 1
    return ImportOutcome(rows_written=rows, target=spec.target)


def _coerce_dizionario(payload: Any) -> list[tuple[str, str]]:
    """Accept either ``{code: label, ...}`` or ``[{code, label}, ...]``."""
    pairs: list[tuple[str, str]] = []
    if isinstance(payload, dict):
        for code, label in payload.items():
            pairs.append((str(code), str(label)))
    elif isinstance(payload, list):
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            code = entry.get("code") or entry.get("id")
            label = entry.get("label") or entry.get("name") or entry.get("description")
            if code is None or label is None:
                continue
            pairs.append((str(code), str(label)))
    return pairs


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------
async def import_dataset(
    conn: asyncpg.Connection,
    *,
    spec: DatasetSpec,
    extracted: list[Path],
    dataset_version_id: int | None,
) -> ImportOutcome:
    """Pick the right importer based on the manifest entry's target."""
    if spec.target == "pai_landslide_hazard":
        return await _import_pai_shapefile(
            conn, spec=spec, extracted=extracted, dataset_version_id=dataset_version_id
        )
    if spec.target == "idraulica_hazard":
        # Same shape as PAI — reuse the importer pointed at the alt table.
        outcome = await _import_pai_shapefile(
            conn, spec=spec, extracted=extracted, dataset_version_id=dataset_version_id
        )
        return ImportOutcome(
            rows_written=outcome.rows_written,
            target=spec.target,
            notes="idraulica (out of V1 landslide scope)",
        )
    if spec.target == "iffi_landslides":
        return await _import_iffi_shapefile(
            conn, spec=spec, extracted=extracted, dataset_version_id=dataset_version_id
        )
    if spec.target in _LOOKUP_TABLES:
        if not extracted:
            raise ValueError(f"{spec.name}: no files extracted from JSON source")
        return await _import_dizionario(conn, spec=spec, json_path=extracted[0])
    raise ValueError(f"{spec.name}: no importer wired for target {spec.target!r}")


__all__ = ["ImportOutcome", "import_dataset"]
