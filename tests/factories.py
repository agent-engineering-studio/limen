"""Costruttori condivisi per i DTO che i test usano ovunque.

Nati con la Fase 2 (#62): `CellRiskRecord` porta ora il breakdown tipizzato
del pericolo invece dei componenti frana appiattiti, e otto file di test
avevano ognuno la propria copia dello stesso boilerplate. Una factory sola
significa che il prossimo cambio di forma si fa in un posto.
"""

from __future__ import annotations

from limen.core.models.context import CellRiskRecord
from limen.core.models.hazard import HazardType
from limen.core.models.risk import (
    ComponentBreakdown,
    FireWeatherState,
    KinematicBreakdown,
    MeteoBreakdown,
    RiskLevel,
    StaticBreakdown,
    WildfireBreakdown,
)

NEUTRAL_STATIC = StaticBreakdown(
    susc_ispra=0.0, iffi_density=0.0, slope=0.0, pai=0.0, litho_weight=0.0
)
NEUTRAL_METEO = MeteoBreakdown(caine_excess=0.0, caine_norm=0.0, api_factor=0.5, soil_factor=0.5)


def landslide_breakdown(
    *,
    s: float = 0.0,
    m: float = 0.0,
    e: float = 0.0,
    f: float = 0.0,
    h: float = 0.0,
    k: float = 0.0,
    static_terms: StaticBreakdown | None = None,
    meteo_terms: MeteoBreakdown | None = None,
    kinematic_terms: KinematicBreakdown | None = None,
) -> ComponentBreakdown:
    return ComponentBreakdown(
        s=s,
        m=m,
        e=e,
        f=f,
        h=h,
        k=k,
        static_terms=static_terms or NEUTRAL_STATIC,
        meteo_terms=meteo_terms or NEUTRAL_METEO,
        kinematic_terms=kinematic_terms,
    )


def landslide_record(
    cell_id: str,
    *,
    score: float,
    level: RiskLevel,
    s: float = 0.0,
    m: float = 0.0,
    e: float = 0.0,
    f: float = 0.0,
    h: float = 0.0,
    k: float = 0.0,
    static_terms: StaticBreakdown | None = None,
    meteo_terms: MeteoBreakdown | None = None,
    kinematic_terms: KinematicBreakdown | None = None,
    monitored: bool = False,
    hard_escalation: bool = False,
) -> CellRiskRecord:
    return CellRiskRecord(
        cell_id=cell_id,
        hazard_type=HazardType.LANDSLIDE,
        score=score,
        level=level,
        breakdown=landslide_breakdown(
            s=s,
            m=m,
            e=e,
            f=f,
            h=h,
            k=k,
            static_terms=static_terms,
            meteo_terms=meteo_terms,
            kinematic_terms=kinematic_terms,
        ),
        monitored=monitored,
        hard_escalation=hard_escalation,
    )


def wildfire_record(
    cell_id: str,
    *,
    score: float,
    level: RiskLevel,
    fwi_norm: float = 0.0,
    fuel: float = 0.0,
    slope: float = 0.0,
    fire_weather: FireWeatherState | None = None,
    spinup: bool = False,
) -> CellRiskRecord:
    return CellRiskRecord(
        cell_id=cell_id,
        hazard_type=HazardType.WILDFIRE,
        score=score,
        level=level,
        breakdown=WildfireBreakdown(
            fwi_norm=fwi_norm,
            fuel=fuel,
            slope=slope,
            fire_weather=fire_weather,
            spinup=spinup,
        ),
    )


__all__ = [
    "NEUTRAL_METEO",
    "NEUTRAL_STATIC",
    "landslide_breakdown",
    "landslide_record",
    "wildfire_record",
]
