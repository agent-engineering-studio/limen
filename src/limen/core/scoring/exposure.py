"""Fattore di esposizione per la priorità degli alert.

``priority = score * (1 + fattore)``: una frana sopra un paese o una
statale conta più di una identica su un versante disabitato. Funzione
pura — il chiamante carica i dati da ``cell_static_factors``, le soglie
vengono dal blocco ``exposure`` di ``regional_thresholds.yaml``. Unica
implementazione condivisa da ``/api/alerts`` e dal dispatcher: NON tocca
mai score o breakdown.
"""

from __future__ import annotations

from limen.core.scoring.regional_thresholds import ExposureBlock


def _format_distance_it(meters: float) -> str:
    if meters < 100.0:
        return "meno di 100 m"
    if meters < 1000.0:
        return f"{round(meters / 10) * 10:.0f} m"
    return f"{meters / 1000.0:.1f}".replace(".", ",") + " km"


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

    Con le distanze OSM presenti il termine infrastrutture è graduato
    ("statale a 180 m" pesa più di "statale a 800 m"); con entrambe NULL
    si degrada ai flag CORINE 12x, preservando il comportamento pre-OSM.
    """
    factor = 0.0
    tags: list[str] = []

    if urban_here:
        factor += cfg.urban_here
        tags.append("abitato")
    elif urban_near:
        factor += cfg.urban_near
        tags.append("vicino abitato")

    if dist_road_m is not None:
        if dist_road_m <= cfg.road_strong_m:
            factor += cfg.road_strong
            tags.append(f"{_road_label(road_class)} a {_format_distance_it(dist_road_m)}")
        elif dist_road_m <= cfg.road_medium_m:
            factor += cfg.road_medium
            tags.append(f"{_road_label(road_class)} a {_format_distance_it(dist_road_m)}")
    if dist_rail_m is not None:
        if dist_rail_m <= cfg.rail_strong_m:
            factor += cfg.rail_strong
            tags.append(f"ferrovia a {_format_distance_it(dist_rail_m)}")
        elif dist_rail_m <= cfg.rail_medium_m:
            factor += cfg.rail_medium
            tags.append(f"ferrovia a {_format_distance_it(dist_rail_m)}")

    if dist_road_m is None and dist_rail_m is None:
        if infra_here:
            factor += cfg.infra_here_fallback
            tags.append("infrastrutture")
        elif infra_near:
            factor += cfg.infra_near_fallback
            tags.append("infrastrutture vicine")

    return min(factor, cfg.cap), tags


__all__ = ["exposure_factor"]
