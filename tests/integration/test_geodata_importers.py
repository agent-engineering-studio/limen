"""Geo-Data Service — importer correctness on small shapefile fixtures.

Spins up the dedicated geodata PostGIS container, generates a tiny
shapefile via pyogrio, and verifies that :func:`import_dataset`:

* writes the expected number of rows,
* normalises geometries to EPSG:4326 and makes them valid,
* maps the PAI ladder (``AA/P1..P4`` + unknowns → ``UNKNOWN``),
* uses the composite ``id`` for IFFI features so the same logical
  feature in two layers (line + poly + aree + dgpv) never collides,
* decodes IFFI Dizionario JSONs into the lookup tables.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import asyncpg
import pytest

from geodata.init.importers import import_dataset
from geodata.manifest import DatasetFormat, DatasetSpec

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------
def _spec(**overrides: Any) -> DatasetSpec:
    base: dict[str, Any] = {
        "name": "pai_frane",
        "url": "https://idrogeo.isprambiente.it/opendata/wms/Mosaicatura_ISPRA_2020_2021_aree_pericolosita_frana_PAI.zip",
        "format": DatasetFormat.SHAPEFILE_ZIP.value,
        "target": "pai_landslide_hazard",
        "enabled": True,
    }
    base.update(overrides)
    return DatasetSpec.model_validate(base)


def _write_shapefile(*, dest: Path, rows: list[dict[str, Any]]) -> list[Path]:
    """Write a tiny shapefile via pyogrio and return its sidecar files."""
    import geopandas as gpd
    import pyogrio

    geoms = [r.pop("geometry") for r in rows]
    gdf = gpd.GeoDataFrame(rows, geometry=geoms, crs="EPSG:4326")
    pyogrio.write_dataframe(gdf, str(dest), driver="ESRI Shapefile")
    return sorted(dest.parent.glob(f"{dest.stem}.*"))


def _poly(lon: float, lat: float, side: float = 0.01) -> Any:
    from shapely.geometry import Polygon

    return Polygon(
        [
            (lon, lat),
            (lon + side, lat),
            (lon + side, lat + side),
            (lon, lat + side),
            (lon, lat),
        ]
    )


def _line(start: tuple[float, float], end: tuple[float, float]) -> Any:
    from shapely.geometry import LineString

    return LineString([start, end])


# ---------------------------------------------------------------------------
# PAI shapefile import
# ---------------------------------------------------------------------------
async def test_import_pai_writes_rows_with_correct_srid_and_classes(
    geodata_conn: asyncpg.Connection, tmp_path: Path
) -> None:
    pyogrio = pytest.importorskip("pyogrio")
    _ = pyogrio
    rows = [
        {
            "pai_id": "PAI-1",
            "classe_pai": "P3",
            "autorita": "AdB-X",
            "geometry": _poly(16.86, 41.12),
        },
        {
            "pai_id": "PAI-2",
            "classe_pai": "p1",
            "autorita": "AdB-X",
            "geometry": _poly(16.90, 41.12),
        },
        {
            "pai_id": "PAI-3",
            "classe_pai": "weird",
            "autorita": "AdB-X",
            "geometry": _poly(16.95, 41.12),
        },
    ]
    extracted = _write_shapefile(dest=tmp_path / "pai.shp", rows=rows)

    outcome = await import_dataset(
        geodata_conn,
        spec=_spec(),
        extracted=extracted,
        dataset_version_id=None,
    )
    assert outcome.rows_written == 3

    db_rows = await geodata_conn.fetch(
        "SELECT pai_id, hazard_class, ST_SRID(geom) AS srid, ST_IsValid(geom) AS valid "
        "FROM pai_landslide_hazard ORDER BY pai_id"
    )
    assert {r["pai_id"] for r in db_rows} == {"PAI-1", "PAI-2", "PAI-3"}
    classes = {r["pai_id"]: r["hazard_class"] for r in db_rows}
    # Case-insensitive normalisation + UNKNOWN survives instead of being dropped.
    assert classes == {"PAI-1": "P3", "PAI-2": "P1", "PAI-3": "UNKNOWN"}
    # Geometry validity + SRID guarantees.
    for r in db_rows:
        assert int(r["srid"]) == 4326
        assert r["valid"] is True


async def test_import_pai_is_idempotent_on_id(
    geodata_conn: asyncpg.Connection, tmp_path: Path
) -> None:
    """Re-running the same shapefile must not duplicate rows — UPSERT semantics."""
    rows = [
        {
            "pai_id": "PAI-1",
            "classe_pai": "P2",
            "autorita": "AdB-X",
            "geometry": _poly(16.86, 41.12),
        },
    ]
    extracted = _write_shapefile(dest=tmp_path / "pai.shp", rows=rows)
    spec = _spec()

    o1 = await import_dataset(geodata_conn, spec=spec, extracted=extracted, dataset_version_id=None)
    o2 = await import_dataset(geodata_conn, spec=spec, extracted=extracted, dataset_version_id=None)
    assert o1.rows_written == 1
    assert o2.rows_written == 1
    n = await geodata_conn.fetchval("SELECT COUNT(*) FROM pai_landslide_hazard")
    assert int(n) == 1


async def test_import_pai_aborts_when_shapefile_missing(
    geodata_conn: asyncpg.Connection, tmp_path: Path
) -> None:
    """Extracted fileset without a .shp must raise so the runner skips THIS dataset."""
    fake_zip_payload = [
        tmp_path / "pai.dbf",
        tmp_path / "pai.shx",
    ]
    for p in fake_zip_payload:
        p.write_bytes(b"\x00")
    with pytest.raises(ValueError, match="shapefile"):
        await import_dataset(
            geodata_conn,
            spec=_spec(),
            extracted=fake_zip_payload,
            dataset_version_id=None,
        )


# ---------------------------------------------------------------------------
# IFFI shapefile import — composite id + geom_type inference
# ---------------------------------------------------------------------------
async def test_import_iffi_composite_id_separates_layers(
    geodata_conn: asyncpg.Connection, tmp_path: Path
) -> None:
    pyogrio = pytest.importorskip("pyogrio")
    _ = pyogrio
    line_shp = _write_shapefile(
        dest=tmp_path / "iffi_puglia_piff_line.shp",
        rows=[
            {
                "iffi_id": "I001",
                "movement": "scivolamento",
                "stato": "attivo",
                "geometry": _line((16.86, 41.12), (16.88, 41.14)),
            }
        ],
    )
    poly_shp = _write_shapefile(
        dest=tmp_path / "iffi_puglia_piff_poly.shp",
        rows=[
            {
                "iffi_id": "I001",
                "movement": "scivolamento",
                "stato": "attivo",
                "geometry": _poly(16.86, 41.12),
            }
        ],
    )

    spec_line = DatasetSpec.model_validate(
        {
            "name": "iffi_puglia_piff_line",
            "url": "https://idrogeo.isprambiente.it/opendata/iffi/puglia/iffi_puglia_piff_line.zip",
            "format": "shapefile-zip",
            "target": "iffi_landslides",
            "region": "puglia",
            "enabled": True,
        }
    )
    spec_poly = DatasetSpec.model_validate(
        {
            "name": "iffi_puglia_piff_poly",
            "url": "https://idrogeo.isprambiente.it/opendata/iffi/puglia/iffi_puglia_piff_poly.zip",
            "format": "shapefile-zip",
            "target": "iffi_landslides",
            "region": "puglia",
            "enabled": True,
        }
    )

    await import_dataset(geodata_conn, spec=spec_line, extracted=line_shp, dataset_version_id=None)
    await import_dataset(geodata_conn, spec=spec_poly, extracted=poly_shp, dataset_version_id=None)

    rows = await geodata_conn.fetch(
        "SELECT id, iffi_id, region, geom_type FROM iffi_landslides ORDER BY id"
    )
    # The same upstream IFFI id ("I001") survives in BOTH layers because the
    # composite primary key is `{region}|{iffi_id}|{geom_type}`.
    assert {r["id"] for r in rows} == {
        "puglia|I001|piff_line",
        "puglia|I001|piff_poly",
    }
    assert {r["iffi_id"] for r in rows} == {"I001"}
    assert {r["geom_type"] for r in rows} == {"piff_line", "piff_poly"}
    assert {r["region"] for r in rows} == {"puglia"}


async def test_import_iffi_requires_region(
    geodata_conn: asyncpg.Connection, tmp_path: Path
) -> None:
    """An IFFI manifest entry without `region` must abort early."""
    extracted = _write_shapefile(
        dest=tmp_path / "iffi_no_region_piff_poly.shp",
        rows=[
            {"iffi_id": "I999", "movement": "x", "geometry": _poly(16.0, 41.0)},
        ],
    )
    bad_spec = DatasetSpec.model_validate(
        {
            "name": "iffi_no_region_piff_poly",
            "url": "https://idrogeo.isprambiente.it/opendata/iffi/no_region/iffi_no_region_piff_poly.zip",
            "format": "shapefile-zip",
            "target": "iffi_landslides",
            "region": None,
            "enabled": True,
        }
    )
    with pytest.raises(ValueError, match="region"):
        await import_dataset(
            geodata_conn, spec=bad_spec, extracted=extracted, dataset_version_id=None
        )


# ---------------------------------------------------------------------------
# Dizionario JSON import
# ---------------------------------------------------------------------------
async def test_import_dizionario_from_dict_payload(
    geodata_conn: asyncpg.Connection, tmp_path: Path
) -> None:
    import json

    dest = tmp_path / "movimento.json"
    dest.write_text(
        json.dumps({"FRA-001": "Scivolamento rotazionale", "FRA-002": "Crollo"}),
        encoding="utf-8",
    )
    spec = DatasetSpec.model_validate(
        {
            "name": "iffi_dizionari_movimento",
            "url": "https://idrogeo.isprambiente.it/opendata/iffi/dizionari/movimento.json",
            "format": "json",
            "target": "iffi_lookup_movements",
            "enabled": True,
        }
    )
    outcome = await import_dataset(
        geodata_conn, spec=spec, extracted=[dest], dataset_version_id=None
    )
    assert outcome.rows_written == 2
    rows = await geodata_conn.fetch("SELECT code, label FROM iffi_lookup_movements ORDER BY code")
    assert [(r["code"], r["label"]) for r in rows] == [
        ("FRA-001", "Scivolamento rotazionale"),
        ("FRA-002", "Crollo"),
    ]


async def test_import_dizionario_replaces_existing(
    geodata_conn: asyncpg.Connection, tmp_path: Path
) -> None:
    """Dizionari are tiny lookups — re-import is a replace-all, not an append."""
    import json

    spec = DatasetSpec.model_validate(
        {
            "name": "iffi_dizionari_movimento",
            "url": "https://idrogeo.isprambiente.it/opendata/iffi/dizionari/movimento.json",
            "format": "json",
            "target": "iffi_lookup_movements",
            "enabled": True,
        }
    )
    p1 = tmp_path / "first.json"
    p1.write_text(json.dumps({"A": "alpha", "B": "beta"}), encoding="utf-8")
    await import_dataset(geodata_conn, spec=spec, extracted=[p1], dataset_version_id=None)

    p2 = tmp_path / "second.json"
    p2.write_text(json.dumps({"B": "BETA-NEW", "C": "gamma"}), encoding="utf-8")
    await import_dataset(geodata_conn, spec=spec, extracted=[p2], dataset_version_id=None)

    rows = await geodata_conn.fetch("SELECT code, label FROM iffi_lookup_movements ORDER BY code")
    # Old "A" was wiped by the replace-all; updated "B" reflects the latest label.
    assert [(r["code"], r["label"]) for r in rows] == [
        ("B", "BETA-NEW"),
        ("C", "gamma"),
    ]


async def test_import_dispatcher_rejects_unknown_target(
    geodata_conn: asyncpg.Connection, tmp_path: Path
) -> None:
    """An unrecognised `target` table must error explicitly."""
    bad_spec = DatasetSpec.model_validate(
        {
            "name": "iffi_dizionari_movimento",
            "url": "https://idrogeo.isprambiente.it/opendata/iffi/dizionari/movimento.json",
            "format": "json",
            "target": "iffi_lookup_movements",
            "enabled": True,
        }
    )
    # Use object.__setattr__ to bypass the frozen model and inject an
    # unrecognised target — easier than instantiating a new model where
    # the validator would block us.
    object.__setattr__(bad_spec, "target", "not_a_real_table")
    with pytest.raises(ValueError, match="no importer wired"):
        await import_dataset(
            geodata_conn, spec=bad_spec, extracted=[tmp_path / "noop"], dataset_version_id=None
        )
