"""Static-bootstrap orchestrator tests.

Seeds a tiny AOI + grid, inserts a few synthetic IFFI/PAI rows, runs
`bootstrap_static_for_aoi`, and asserts the achievable factors are
populated. DEM/CORINE/lithology are documented NULLs.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from shapely.geometry import LineString, MultiPolygon, Point, Polygon

from limen.data.db import acquire
from limen.data.repos.aoi_repo import upsert_aoi
from limen.data.repos.cell_static_factors_repo import count_factors, get_for_cell
from limen.data.repos.flood_repo import FloodHazard
from limen.data.repos.flood_repo import upsert_many as upsert_flood
from limen.data.repos.grid_repo import count_grid_cells, generate_and_store_grid
from limen.data.repos.iffi_repo import IFFILandslide
from limen.data.repos.iffi_repo import upsert_many as upsert_iffi
from limen.data.repos.pai_repo import PAIHazard
from limen.data.repos.pai_repo import upsert_many as upsert_pai
from limen.integrations.osm import sync_osm_infrastructure
from limen.integrations.static_bootstrap import bootstrap_static_for_aoi

pytestmark = pytest.mark.integration

_AOI = Polygon(
    [
        (16.86, 41.12),
        (16.92, 41.12),
        (16.92, 41.17),
        (16.86, 41.17),
        (16.86, 41.12),
    ]
)

_AOI_ID = "test-bootstrap-bari"

# IFFI point near (16.88, 41.14)
_IFFI_NEAR = IFFILandslide(
    id="iffi-near",
    movement_type="scivolamento",
    state="attivo",
    velocity_class=None,
    occurrence_date=None,
    geom=Point(16.88, 41.14),
    attributes={"src": "test"},
)
# Far enough that no cell should be within 500m of it
_IFFI_FAR = IFFILandslide(
    id="iffi-far",
    movement_type="colata",
    state="quiescente",
    velocity_class=None,
    occurrence_date=None,
    geom=Point(16.95, 41.20),
    attributes={"src": "test"},
)

# PAI polygon covering roughly the south-west quadrant
_PAI_P3 = PAIHazard(
    id="pai-p3",
    hazard_class="P3",
    authority="test",
    geom=MultiPolygon(
        [
            Polygon(
                [
                    (16.86, 41.12),
                    (16.89, 41.12),
                    (16.89, 41.14),
                    (16.86, 41.14),
                    (16.86, 41.12),
                ]
            )
        ]
    ),
    attributes={"src": "test"},
)


async def _seed(reset_db: None) -> None:
    await upsert_aoi(id=_AOI_ID, name="test bootstrap", kind="test", geom=_AOI)
    await generate_and_store_grid(_AOI_ID)
    await upsert_iffi([_IFFI_NEAR, _IFFI_FAR])
    await upsert_pai([_PAI_P3])


async def test_bootstrap_populates_cells(reset_db: None) -> None:
    await _seed(reset_db)
    total_cells = await count_grid_cells(_AOI_ID)
    assert total_cells > 0

    result = await bootstrap_static_for_aoi(_AOI_ID)
    assert result["cells_with_factors"] == total_cells
    assert await count_factors() == total_cells


async def test_bootstrap_computes_iffi_density_and_distance(reset_db: None) -> None:
    """At least one cell sits near the IFFI point and should have density >= 1."""
    await _seed(reset_db)
    await bootstrap_static_for_aoi(_AOI_ID)

    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT MAX(iffi_density_500) AS max_density,
                   MIN(distance_to_iffi_m) AS min_distance,
                   COUNT(*) FILTER (WHERE iffi_density_500 IS NOT NULL) AS rows_with_density
            FROM cell_static_factors c
            JOIN grid_cells g ON g.id = c.cell_id
            WHERE g.aoi_id = $1
            """,
            _AOI_ID,
        )
    assert row is not None
    assert int(row["rows_with_density"]) > 0
    assert float(row["max_density"]) >= 1.0
    assert row["min_distance"] is not None
    assert float(row["min_distance"]) < 1_000.0  # at least one cell is within 1 km of an IFFI


async def test_bootstrap_writes_pai_class_norm(reset_db: None) -> None:
    await _seed(reset_db)
    await bootstrap_static_for_aoi(_AOI_ID)

    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT MAX(pai_class_norm) AS max_pai,
                   COUNT(*) FILTER (WHERE pai_class_norm IS NOT NULL) AS rows_with_pai
            FROM cell_static_factors c
            JOIN grid_cells g ON g.id = c.cell_id
            WHERE g.aoi_id = $1
            """,
            _AOI_ID,
        )
    assert row is not None
    assert int(row["rows_with_pai"]) > 0
    # P3 → 0.80 normalised
    assert float(row["max_pai"]) == pytest.approx(0.80)


_FLOOD_GEOM = MultiPolygon(
    [
        Polygon(
            [
                (16.89, 41.14),
                (16.92, 41.14),
                (16.92, 41.17),
                (16.89, 41.17),
                (16.89, 41.14),
            ]
        )
    ]
)


async def test_bootstrap_writes_flood_hazard_from_subdiv(reset_db: None) -> None:
    """Repo upsert keeps flood_hazard_subdiv in lockstep; aggregation reads it."""
    await _seed(reset_db)
    await upsert_flood(
        [
            FloodHazard(
                id="flood-p2", hazard_class="P2", geom=_FLOOD_GEOM, attributes={"src": "test"}
            )
        ]
    )
    await bootstrap_static_for_aoi(_AOI_ID)

    async with acquire() as conn:
        subdiv = await conn.fetchval(
            "SELECT count(*) FROM flood_hazard_subdiv WHERE id = 'flood-p2'"
        )
        row = await conn.fetchrow(
            """
            SELECT MAX(flood_hazard_norm) AS max_flood,
                   COUNT(*) FILTER (WHERE flood_hazard_norm IS NOT NULL) AS rows_with_flood
            FROM cell_static_factors c
            JOIN grid_cells g ON g.id = c.cell_id
            WHERE g.aoi_id = $1
            """,
            _AOI_ID,
        )
    assert int(subdiv) >= 1
    assert row is not None
    assert int(row["rows_with_flood"]) > 0
    # P2 → 0.60 normalised (PAI_CLASS_TO_NORM ladder)
    assert float(row["max_flood"]) == pytest.approx(0.60)


async def test_bootstrap_backfills_flood_subdiv(reset_db: None) -> None:
    """Rows inserted before migration 014 (raw flood_hazard only) get healed."""
    await _seed(reset_db)
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO flood_hazard (id, hazard_class, hazard_class_norm, geom)
            VALUES ('flood-legacy', 'P3', 0.80, ST_SetSRID($1::geometry, 4326))
            """,
            _FLOOD_GEOM,
        )
    await bootstrap_static_for_aoi(_AOI_ID)

    async with acquire() as conn:
        subdiv = await conn.fetchval(
            "SELECT count(*) FROM flood_hazard_subdiv WHERE id = 'flood-legacy'"
        )
        max_flood = await conn.fetchval(
            """
            SELECT MAX(flood_hazard_norm)
            FROM cell_static_factors c
            JOIN grid_cells g ON g.id = c.cell_id
            WHERE g.aoi_id = $1
            """,
            _AOI_ID,
        )
    assert int(subdiv) >= 1
    assert float(max_flood) == pytest.approx(0.80)


async def test_bootstrap_leaves_dem_fields_null(reset_db: None) -> None:
    """DEM/CORINE/lithology not wired up yet — must remain NULL, not crash."""
    await _seed(reset_db)
    await bootstrap_static_for_aoi(_AOI_ID)

    cells = await count_grid_cells(_AOI_ID)
    async with acquire() as conn:
        sample_id = await conn.fetchval(
            "SELECT id FROM grid_cells WHERE aoi_id = $1 LIMIT 1", _AOI_ID
        )
    assert cells > 0
    assert sample_id is not None

    factors = await get_for_cell(str(sample_id))
    assert factors is not None
    assert factors.slope_deg is None
    assert factors.aspect_deg is None
    assert factors.elevation_m is None
    assert factors.twi is None
    assert factors.landuse_code is None
    assert factors.lithology is None


async def test_osm_sync_and_distances(reset_db: None, tmp_path: Path) -> None:
    """OSM network loaded from vector files → per-cell road/rail distances."""
    import geopandas as gpd

    await _seed(reset_db)

    # A primary road crossing the AOI north-south and a railway well
    # outside it (~45 km east) but under the 50 km cap.
    roads_path = tmp_path / "roads.gpkg"
    gpd.GeoDataFrame(
        {"highway": ["primary"]},
        geometry=[LineString([(16.88, 41.10), (16.88, 41.19)])],
        crs="EPSG:4326",
    ).to_file(roads_path)
    rails_path = tmp_path / "rails.gpkg"
    gpd.GeoDataFrame(
        {"dummy": [1]},
        geometry=[LineString([(17.40, 41.10), (17.40, 41.19)])],
        crs="EPSG:4326",
    ).to_file(rails_path)

    written = await sync_osm_infrastructure(roads_path=roads_path, railways_path=rails_path)
    assert written == 2

    await bootstrap_static_for_aoi(_AOI_ID)

    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT MIN(distance_to_road_m) AS min_road,
                   MIN(distance_to_rail_m) AS min_rail,
                   COUNT(*) FILTER (WHERE distance_to_road_m IS NULL) AS null_road
            FROM cell_static_factors c
            JOIN grid_cells g ON g.id = c.cell_id
            WHERE g.aoi_id = $1
            """,
            _AOI_ID,
        )
        near_class = await conn.fetchval(
            """
            SELECT c.nearest_road_class
            FROM cell_static_factors c
            JOIN grid_cells g ON g.id = c.cell_id
            WHERE g.aoi_id = $1
            ORDER BY c.distance_to_road_m ASC
            LIMIT 1
            """,
            _AOI_ID,
        )
    assert row is not None
    assert int(row["null_road"]) == 0
    # The road crosses the AOI: the nearest cell centroid sits within ~1 km.
    assert float(row["min_road"]) < 1_500.0
    # The railway is ~40+ km east: far, but below the 50 km cap.
    assert 20_000.0 < float(row["min_rail"]) < 50_000.0
    assert near_class == "primary"


async def test_osm_unset_leaves_distances_null(
    reset_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No LIMEN_OSM_* files → clean no-op, distance columns stay NULL."""
    monkeypatch.delenv("LIMEN_OSM_ROADS", raising=False)
    monkeypatch.delenv("LIMEN_OSM_RAILWAYS", raising=False)
    await _seed(reset_db)
    written = await sync_osm_infrastructure()
    assert written == 0

    await bootstrap_static_for_aoi(_AOI_ID)
    async with acquire() as conn:
        non_null = await conn.fetchval(
            """
            SELECT COUNT(*) FILTER (
                WHERE distance_to_road_m IS NOT NULL OR distance_to_rail_m IS NOT NULL
            )
            FROM cell_static_factors c
            JOIN grid_cells g ON g.id = c.cell_id
            WHERE g.aoi_id = $1
            """,
            _AOI_ID,
        )
    assert int(non_null) == 0
