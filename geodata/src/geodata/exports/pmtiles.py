"""``limen geodata make-pmtiles`` — tippecanoe-driven PMTiles export.

The pipeline runs in two passes per layer:

1. Stream a GeoJSON feature collection out of the geodata PostGIS
   (one file per layer) into the configured staging directory.
2. Invoke the system ``tippecanoe`` binary to convert that GeoJSON
   into a ``.pmtiles`` file in the shared static volume — the map
   consumes it without ever hitting Postgres at view time.

``tippecanoe`` is a system binary (installed in the geodata Docker
image, not as a Python dep). Its absence degrades to a logged warning
+ non-zero exit so the operator notices.

Output paths:

* ``$GEODATA_GEOJSON_DIR`` (default ``/var/lib/geodata/geojson``)
* ``$GEODATA_PMTILES_DIR`` (default ``/var/lib/geodata/pmtiles`` —
  shared volume with the static-tiles serving container)
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import structlog

from geodata.db import connect as connect_geodata

_log: structlog.stdlib.BoundLogger = structlog.get_logger("geodata.exports.pmtiles")


@dataclass(frozen=True, slots=True)
class TileLayer:
    """One tippecanoe layer spec."""

    name: str
    """``-l`` layer name inside the .pmtiles archive."""
    sql: str
    """SELECT statement returning ``id``, ``properties_json``, ``geometry_text``
    in EPSG:4326. The exporter wraps it into a GeoJSON FeatureCollection."""
    output_stem: str
    """File stem for both the staging GeoJSON and the final .pmtiles."""
    min_zoom: int = 6
    max_zoom: int = 12
    drop_densest_as_needed: bool = True


_DEFAULT_LAYERS: tuple[TileLayer, ...] = (
    TileLayer(
        name="pai",
        sql=(
            "SELECT pai_id AS id, attributes AS properties, "
            "ST_AsGeoJSON(geom)::jsonb AS geometry FROM pai_landslide_hazard "
            "WHERE hazard_class IN ('AA','P1','P2','P3','P4')"
        ),
        output_stem="pai_landslide_hazard",
    ),
    TileLayer(
        name="iffi",
        sql=(
            "SELECT id, attributes AS properties, "
            "ST_AsGeoJSON(geom)::jsonb AS geometry FROM iffi_landslides"
        ),
        output_stem="iffi_landslides",
        min_zoom=7,
        max_zoom=13,
    ),
)


def _staging_dir() -> Path:
    return Path(os.environ.get("GEODATA_GEOJSON_DIR", "/var/lib/geodata/geojson"))


def _pmtiles_dir() -> Path:
    return Path(os.environ.get("GEODATA_PMTILES_DIR", "/var/lib/geodata/pmtiles"))


async def _write_layer_geojson(layer: TileLayer, *, dest: Path) -> int:
    """Stream a FeatureCollection to disk. Returns rows written."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    async with connect_geodata() as conn:
        # GeoJSON FeatureCollection — written line-by-line so memory
        # footprint stays bounded even for the 930k-polygon PAI mosaic.
        with dest.open("w", encoding="utf-8") as fh:
            fh.write('{"type":"FeatureCollection","features":[')
            first = True
            async for row in _stream(conn, layer.sql):
                if not first:
                    fh.write(",")
                first = False
                fh.write(_feature_to_json(row))
                written += 1
            fh.write("]}")
    return written


async def _stream(conn, sql: str):  # type: ignore[no-untyped-def]
    """Async iterator over the rows of ``sql``."""
    async with conn.transaction():
        async for row in conn.cursor(sql, prefetch=500):
            yield row


def _feature_to_json(row) -> str:  # type: ignore[no-untyped-def]
    """Build one GeoJSON feature from a (id, properties, geometry) row."""
    props = row["properties"]
    if isinstance(props, str):
        props = json.loads(props)
    geom = row["geometry"]
    if isinstance(geom, str):
        geom = json.loads(geom)
    return json.dumps(
        {
            "type": "Feature",
            "id": str(row["id"]),
            "properties": props or {},
            "geometry": geom,
        },
        separators=(",", ":"),
        default=str,
    )


def _tippecanoe_available() -> bool:
    return shutil.which("tippecanoe") is not None


async def _run_tippecanoe(
    *,
    geojson_path: Path,
    pmtiles_path: Path,
    layer: TileLayer,
) -> int:
    pmtiles_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "tippecanoe",
        "-o",
        str(pmtiles_path),
        "-l",
        layer.name,
        f"--minimum-zoom={layer.min_zoom}",
        f"--maximum-zoom={layer.max_zoom}",
        "--force",
    ]
    if layer.drop_densest_as_needed:
        cmd.append("--drop-densest-as-needed")
    cmd.append(str(geojson_path))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        _log.warning(
            "geodata.tippecanoe.failed",
            layer=layer.name,
            exit_code=proc.returncode,
            stderr=stderr.decode("utf-8", "replace")[:2000],
        )
        return int(proc.returncode or 1)
    _log.info(
        "geodata.tippecanoe.done",
        layer=layer.name,
        pmtiles=str(pmtiles_path),
        stdout_tail=stdout.decode("utf-8", "replace")[-200:],
    )
    return 0


async def make_pmtiles(
    *,
    layers: tuple[TileLayer, ...] = _DEFAULT_LAYERS,
    staging_dir: Path | None = None,
    pmtiles_dir: Path | None = None,
) -> int:
    """Run the GeoJSON → PMTiles pipeline for every configured layer."""
    if not _tippecanoe_available():
        _log.warning(
            "geodata.make_pmtiles.no_tippecanoe",
            hint="install tippecanoe (apt-get install tippecanoe) — image carries it on the VPS",
        )
        return 1

    staging = staging_dir or _staging_dir()
    out_dir = pmtiles_dir or _pmtiles_dir()
    failures = 0
    for layer in layers:
        geojson_path = staging / f"{layer.output_stem}.geojson"
        try:
            rows = await _write_layer_geojson(layer, dest=geojson_path)
        except Exception as exc:
            failures += 1
            _log.warning(
                "geodata.make_pmtiles.geojson_failed",
                layer=layer.name,
                error=str(exc),
            )
            continue
        if rows == 0:
            _log.info("geodata.make_pmtiles.empty_layer", layer=layer.name)
            continue
        pmtiles_path = out_dir / f"{layer.output_stem}.pmtiles"
        rc = await _run_tippecanoe(
            geojson_path=geojson_path,
            pmtiles_path=pmtiles_path,
            layer=layer,
        )
        if rc != 0:
            failures += 1
    _log.info(
        "geodata.make_pmtiles.done",
        layers=len(layers),
        failures=failures,
        staging_dir=str(staging),
        pmtiles_dir=str(out_dir),
    )
    return 1 if failures else 0


__all__ = ["TileLayer", "make_pmtiles"]
