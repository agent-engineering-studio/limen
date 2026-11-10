"""Per-cell static factors repository.

The static-bootstrap pipeline writes rows here. Every column is nullable
on purpose: when a source dataset is unavailable, the bootstrap skips
that field rather than crashing.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from limen.core.logging import get_logger
from limen.core.models.risk import StaticFactors
from limen.data.db import acquire

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CellStaticFactors:
    cell_id: str
    slope_deg: float | None = None
    aspect_deg: float | None = None
    elevation_m: float | None = None
    twi: float | None = None
    curvature: float | None = None
    lithology: str | None = None
    landuse_code: str | None = None
    litho_weight: float | None = None
    dist_faults_m: float | None = None
    distance_to_iffi_m: float | None = None
    iffi_density_500: float | None = None
    pai_class_norm: float | None = None
    # Phase 12+: flood hazard from the ISPRA Mosaicatura Idraulica.
    flood_hazard_class: str | None = None
    flood_hazard_norm: float | None = None
    # Suolo sigillato (#63) ed esposizione viabilità (#21). Erano nella
    # tabella ma non qui, quindi chi leggeva la riga li trovava assenti: il
    # vettore di feature dell'alluvione (#64) usciva senza il suo secondo
    # predittore e nessuno se ne accorgeva.
    imperviousness_norm: float | None = None
    distance_to_road_m: float | None = None
    # #469, letta dal blocco `terrain` del motore alluvione: lo sfidante deve
    # vederla anche lui (#482).
    quota_sul_fondo_m: float | None = None
    # Interfaccia urbano-foresta (#62) e memoria del fuoco (#66): servono al
    # vettore di feature dell'incendio (#68). Con l'accesso diretto un campo
    # assente è un AttributeError immediato invece di un None silenzioso —
    # che è esattamente come questo è stato trovato.
    wui_proximity_norm: float | None = None
    fire_density: int = 0
    extras: dict[str, Any] | None = None


async def upsert_many(items: Iterable[CellStaticFactors]) -> int:
    """Bulk upsert (single transaction). Returns the count written."""
    items_list = list(items)
    if not items_list:
        return 0
    async with acquire() as conn, conn.transaction():
        for it in items_list:
            extras_json = json.dumps(it.extras or {}, default=str)
            await conn.execute(
                """
                INSERT INTO cell_static_factors (
                    cell_id, slope_deg, aspect_deg, elevation_m, twi, curvature,
                    lithology, landuse_code, litho_weight,
                    dist_faults_m, distance_to_iffi_m, iffi_density_500,
                    pai_class_norm, flood_hazard_class, flood_hazard_norm, extras
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
                    $14, $15, $16::jsonb
                )
                ON CONFLICT (cell_id) DO UPDATE
                SET slope_deg    = COALESCE(EXCLUDED.slope_deg,
                                            cell_static_factors.slope_deg),
                    aspect_deg   = COALESCE(EXCLUDED.aspect_deg,
                                            cell_static_factors.aspect_deg),
                    elevation_m  = COALESCE(EXCLUDED.elevation_m,
                                            cell_static_factors.elevation_m),
                    twi          = COALESCE(EXCLUDED.twi,
                                            cell_static_factors.twi),
                    curvature    = COALESCE(EXCLUDED.curvature,
                                            cell_static_factors.curvature),
                    lithology    = COALESCE(EXCLUDED.lithology,
                                            cell_static_factors.lithology),
                    landuse_code = COALESCE(EXCLUDED.landuse_code,
                                            cell_static_factors.landuse_code),
                    litho_weight = COALESCE(EXCLUDED.litho_weight,
                                            cell_static_factors.litho_weight),
                    dist_faults_m = COALESCE(EXCLUDED.dist_faults_m,
                                             cell_static_factors.dist_faults_m),
                    distance_to_iffi_m = COALESCE(EXCLUDED.distance_to_iffi_m,
                                                  cell_static_factors.distance_to_iffi_m),
                    iffi_density_500 = COALESCE(EXCLUDED.iffi_density_500,
                                                cell_static_factors.iffi_density_500),
                    pai_class_norm = COALESCE(EXCLUDED.pai_class_norm,
                                              cell_static_factors.pai_class_norm),
                    flood_hazard_class = COALESCE(EXCLUDED.flood_hazard_class,
                                                  cell_static_factors.flood_hazard_class),
                    flood_hazard_norm  = COALESCE(EXCLUDED.flood_hazard_norm,
                                                  cell_static_factors.flood_hazard_norm),
                    extras       = cell_static_factors.extras || EXCLUDED.extras,
                    updated_at   = now()
                """,
                it.cell_id,
                it.slope_deg,
                it.aspect_deg,
                it.elevation_m,
                it.twi,
                it.curvature,
                it.lithology,
                it.landuse_code,
                it.litho_weight,
                it.dist_faults_m,
                it.distance_to_iffi_m,
                it.iffi_density_500,
                it.pai_class_norm,
                it.flood_hazard_class,
                it.flood_hazard_norm,
                extras_json,
            )
    log.info("cell_static_factors.upsert_many", count=len(items_list))
    return len(items_list)


async def count_factors() -> int:
    async with acquire() as conn:
        row = await conn.fetchrow("SELECT COUNT(*)::bigint AS n FROM cell_static_factors")
    return int(row["n"]) if row else 0


async def get_for_cell(cell_id: str) -> CellStaticFactors | None:
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT cell_id, slope_deg, aspect_deg, elevation_m, twi, curvature,
                   lithology, landuse_code, litho_weight,
                   dist_faults_m, distance_to_iffi_m, iffi_density_500,
                   pai_class_norm, flood_hazard_class, flood_hazard_norm,
                   imperviousness_norm, distance_to_road_m, quota_sul_fondo_m,
                   wui_proximity_norm, fire_density, extras
            FROM cell_static_factors WHERE cell_id = $1
            """,
            cell_id,
        )
    if row is None:
        return None
    extras = row["extras"]
    if isinstance(extras, str):
        extras = json.loads(extras)
    return CellStaticFactors(
        cell_id=row["cell_id"],
        slope_deg=row["slope_deg"],
        aspect_deg=row["aspect_deg"],
        elevation_m=row["elevation_m"],
        twi=row["twi"],
        curvature=row["curvature"],
        lithology=row["lithology"],
        landuse_code=row["landuse_code"],
        litho_weight=row["litho_weight"],
        dist_faults_m=row["dist_faults_m"],
        distance_to_iffi_m=row["distance_to_iffi_m"],
        iffi_density_500=row["iffi_density_500"],
        pai_class_norm=row["pai_class_norm"],
        flood_hazard_class=row["flood_hazard_class"],
        flood_hazard_norm=row["flood_hazard_norm"],
        imperviousness_norm=row["imperviousness_norm"],
        distance_to_road_m=row["distance_to_road_m"],
        quota_sul_fondo_m=row["quota_sul_fondo_m"],
        wui_proximity_norm=row["wui_proximity_norm"],
        fire_density=int(row["fire_density"] or 0),
        extras=extras or {},
    )


_FATTORI_AOI_SQL = """
SELECT c.cell_id,
       c.slope_deg, c.aspect_deg, c.elevation_m, c.twi, c.curvature,
       c.lithology, c.landuse_code,
       c.litho_weight, c.dist_faults_m,
       c.distance_to_iffi_m, c.iffi_density_500,
       c.pai_class_norm,
       c.flood_hazard_norm,
       c.quota_sul_fondo_m,
       c.imperviousness_norm,
       s.score AS susc_ispra,
       i.insar_velocity_mmy, i.insar_accel_mmy2, i.scatterer_count,
       i.velocita_verticale_mmy, i.velocita_est_mmy, i.stagionalita_verticale_mm,
       ST_X(ST_Centroid(g.geom)) AS lon, ST_Y(ST_Centroid(g.geom)) AS lat
FROM cell_static_factors c
JOIN grid_cells g ON g.id = c.cell_id
LEFT JOIN susceptibility s ON s.cell_id = c.cell_id
LEFT JOIN cell_insar_features i ON i.cell_id = c.cell_id
WHERE g.aoi_id = $1
"""


def _float(x: Any) -> float | None:
    return None if x is None else float(x)


async def fattori_aoi(aoi_id: str) -> list[tuple[StaticFactors, float, float]]:
    """``(StaticFactors, lon, lat)`` per ogni cella dell'AOI, come li legge il motore.

    Lo step ``StaticFactors`` del workflow e ``limen backtest`` leggono da qui:
    il backtest se ne costruiva una versione sua con i soli campi di cui
    pensava avesse bisogno la V1, e mancavano la suscettibilità ISPRA (S) e la
    classe idraulica (H) — la V1 misurata non era quella in produzione — oltre
    a tutto ciò che legge lo sfidante ML (#568).
    """
    async with acquire() as conn:
        rows = await conn.fetch(_FATTORI_AOI_SQL, aoi_id)
    out: list[tuple[StaticFactors, float, float]] = []
    for r in rows:
        sf = StaticFactors(
            cell_id=str(r["cell_id"]),
            susc_ispra=float(r["susc_ispra"]) if r["susc_ispra"] is not None else None,
            iffi_density_500=(
                float(r["iffi_density_500"]) if r["iffi_density_500"] is not None else None
            ),
            distance_to_iffi_m=(
                float(r["distance_to_iffi_m"]) if r["distance_to_iffi_m"] is not None else None
            ),
            slope_deg=float(r["slope_deg"]) if r["slope_deg"] is not None else None,
            aspect_deg=float(r["aspect_deg"]) if r["aspect_deg"] is not None else None,
            elevation_m=float(r["elevation_m"]) if r["elevation_m"] is not None else None,
            twi=float(r["twi"]) if r["twi"] is not None else None,
            curvature=float(r["curvature"]) if r["curvature"] is not None else None,
            lithology=r["lithology"],
            litho_weight=(float(r["litho_weight"]) if r["litho_weight"] is not None else None),
            landuse_code=r["landuse_code"],
            pai_class_norm=(
                float(r["pai_class_norm"]) if r["pai_class_norm"] is not None else None
            ),
            flood_hazard_norm=(
                float(r["flood_hazard_norm"]) if r["flood_hazard_norm"] is not None else None
            ),
            quota_sul_fondo_m=(
                float(r["quota_sul_fondo_m"]) if r["quota_sul_fondo_m"] is not None else None
            ),
            imperviousness_norm=(
                float(r["imperviousness_norm"]) if r["imperviousness_norm"] is not None else None
            ),
            insar_velocity_mmy=_float(r["insar_velocity_mmy"]),
            insar_accel_mmy2=_float(r["insar_accel_mmy2"]),
            insar_scatterer_count=(
                int(r["scatterer_count"]) if r["scatterer_count"] is not None else None
            ),
            velocita_verticale_mmy=_float(r["velocita_verticale_mmy"]),
            velocita_est_mmy=_float(r["velocita_est_mmy"]),
            stagionalita_verticale_mm=_float(r["stagionalita_verticale_mm"]),
        )
        out.append((sf, float(r["lon"]), float(r["lat"])))
    return out
