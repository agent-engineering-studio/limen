"""Fattore di esposizione per la priorità degli alert.

``priority = score * (1 + fattore)``: una frana sopra un paese o una
statale conta più di una identica su un versante disabitato. Funzione
pura — il chiamante carica i dati da ``cell_static_factors``, le soglie
vengono dal blocco ``exposure`` di ``regional_thresholds.yaml``. Unica
implementazione condivisa da ``/api/alerts`` e dal dispatcher: NON tocca
mai score o breakdown.
"""

from __future__ import annotations

from typing import Any

from limen.core.scoring.regional_thresholds import ExposureBlock


def _format_distance_it(meters: float) -> str:
    if meters < 100.0:
        return "meno di 100 m"
    rounded = round(meters / 10) * 10
    if rounded >= 1000:
        return f"{meters / 1000.0:.1f}".replace(".", ",") + " km"
    return f"{rounded:.0f} m"


def _road_label(road_class: str | None) -> str:
    return "autostrada" if road_class == "motorway" else "statale"


def exposure_factor(
    *,
    urban_here: bool,
    urban_near: bool,
    infra_here: bool,
    infra_near: bool,
    dist_road_m: float | None,
    dist_rail_m: float | None,
    road_class: str | None,
    cfg: ExposureBlock,
) -> tuple[float, list[str]]:
    """Fattore in ``[0, cfg.cap]`` + tag italiani per la UI.

    Con le distanze OSM il termine infrastrutture è graduato ("statale a
    180 m" pesa più di "statale a 800 m"). Quando la rete OSM non dà
    contributo — non ingerita (distanze NULL) oppure oltre le bande —
    valgono i flag CORINE 12x: coprono anche ciò che l'estratto
    strade/ferrovie non vede (industriale 121, porti/aeroporti 123-124)
    e preservano il comportamento pre-OSM anche con ingest parziale.
    """
    factor = 0.0
    tags: list[str] = []

    if urban_here:
        factor += cfg.urban_here
        tags.append("abitato")
    elif urban_near:
        factor += cfg.urban_near
        tags.append("vicino abitato")

    osm_factor = 0.0
    if dist_road_m is not None:
        if dist_road_m <= cfg.road_strong_m:
            osm_factor += cfg.road_strong
            tags.append(f"{_road_label(road_class)} a {_format_distance_it(dist_road_m)}")
        elif dist_road_m <= cfg.road_medium_m:
            osm_factor += cfg.road_medium
            tags.append(f"{_road_label(road_class)} a {_format_distance_it(dist_road_m)}")
    if dist_rail_m is not None:
        if dist_rail_m <= cfg.rail_strong_m:
            osm_factor += cfg.rail_strong
            tags.append(f"ferrovia a {_format_distance_it(dist_rail_m)}")
        elif dist_rail_m <= cfg.rail_medium_m:
            osm_factor += cfg.rail_medium
            tags.append(f"ferrovia a {_format_distance_it(dist_rail_m)}")
    factor += osm_factor

    if osm_factor == 0.0:
        if infra_here:
            factor += cfg.infra_here_fallback
            tags.append("infrastrutture")
        elif infra_near:
            factor += cfg.infra_near_fallback
            tags.append("infrastrutture vicine")

    return min(factor, cfg.cap), tags


def exposure_factor_from_row(row: Any, cfg: ExposureBlock) -> tuple[float, list[str]]:
    """Adapter per le righe SQL condivise da ``/api/alerts`` e dispatcher.

    Colonne attese: ``urban_here``, ``urban_near``, ``infra_here``,
    ``infra_near``, ``distance_to_road_m``, ``distance_to_rail_m``,
    ``nearest_road_class``.
    """
    return exposure_factor(
        urban_here=bool(row["urban_here"]),
        urban_near=bool(row["urban_near"]),
        infra_here=bool(row["infra_here"]),
        infra_near=bool(row["infra_near"]),
        dist_road_m=(
            float(row["distance_to_road_m"]) if row["distance_to_road_m"] is not None else None
        ),
        dist_rail_m=(
            float(row["distance_to_rail_m"]) if row["distance_to_rail_m"] is not None else None
        ),
        road_class=row["nearest_road_class"],
        cfg=cfg,
    )


__all__ = ["exposure_factor", "exposure_factor_from_row"]
