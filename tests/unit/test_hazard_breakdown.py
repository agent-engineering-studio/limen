"""Breakdown discriminato per hazard + RiskScore generico (issue #83).

Due proprietà da difendere. La prima è la serializzazione: la colonna
``risk_assessments.factors`` e le risposte API nascono da questi DTO, quindi
un cambio di forma non annunciato romperebbe la mappa pubblica. La seconda è
che un secondo hazard entri nel sistema **senza** toccare codice di
produzione, che è il criterio di accettazione di #57.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

import pytest
from pydantic import Field, ValidationError

from limen.core.models.hazard import DEFAULT_HAZARD, HazardType
from limen.core.models.risk import (
    CellFeatureBundle,
    ComponentBreakdown,
    DynamicInputs,
    HazardBreakdown,
    MeteoBreakdown,
    RiskLevel,
    RiskScore,
    StaticBreakdown,
    StaticFactors,
)
from limen.core.scoring.base import ScoringEngine

_STATIC = StaticBreakdown(susc_ispra=0.4, iffi_density=0.2, slope=0.5, pai=0.3, litho_weight=0.6)
_METEO = MeteoBreakdown(caine_excess=0.1, caine_norm=0.2, api_factor=0.3, soil_factor=0.4)


def _landslide_score() -> RiskScore[ComponentBreakdown]:
    return RiskScore(
        score=0.42,
        level=RiskLevel.Moderate,
        breakdown=ComponentBreakdown(
            s=0.4,
            m=0.3,
            e=0.2,
            f=0.0,
            h=0.1,
            static_terms=_STATIC,
            meteo_terms=_METEO,
        ),
        model_version="test-v1",
    )


def test_landslide_breakdown_keeps_its_shape() -> None:
    """La forma serializzata è quella di prima più il solo discriminante.

    I consumatori a valle leggono `s`/`m`/`e`/`f`/`h`/`k`, `static_terms` e
    `meteo_terms` per nome: se uno di questi cambiasse chiave o tipo, la
    colonna `factors` e il breakdown esposto dall'API smetterebbero di essere
    leggibili dalle righe già scritte.
    """
    dumped = _landslide_score().to_dict()
    breakdown = dumped["breakdown"]
    assert isinstance(breakdown, dict)

    assert set(breakdown) == {
        "hazard_type",
        "s",
        "m",
        "e",
        "f",
        "h",
        "k",
        "static_terms",
        "meteo_terms",
        "kinematic_terms",
    }
    assert breakdown["hazard_type"] == "landslide"
    assert breakdown["s"] == 0.4
    assert breakdown["k"] == 0.0
    assert breakdown["kinematic_terms"] is None
    assert set(breakdown["static_terms"]) == {
        "susc_ispra",
        "iffi_density",
        "slope",
        "pai",
        "litho_weight",
    }
    # Il livello superiore non guadagna nulla.
    assert set(dumped) == {
        "score",
        "level",
        "breakdown",
        "model_version",
        "monitored",
        "hard_escalation",
    }


def test_discriminator_is_fixed_for_landslide() -> None:
    """Non si può etichettare un breakdown frane come un altro hazard."""
    assert (
        ComponentBreakdown(
            s=0.0, m=0.0, e=0.0, f=0.0, h=0.0, static_terms=_STATIC, meteo_terms=_METEO
        ).hazard_type
        is HazardType.LANDSLIDE
    )

    with pytest.raises(ValidationError):
        ComponentBreakdown(
            hazard_type=HazardType.FLOOD,  # type: ignore[arg-type]
            s=0.0,
            m=0.0,
            e=0.0,
            f=0.0,
            h=0.0,
            static_terms=_STATIC,
            meteo_terms=_METEO,
        )


def test_breakdown_stays_frozen_and_closed() -> None:
    """`frozen` ed `extra="forbid"` sopravvivono all'ereditarietà."""
    bd = ComponentBreakdown(
        s=0.0, m=0.0, e=0.0, f=0.0, h=0.0, static_terms=_STATIC, meteo_terms=_METEO
    )
    with pytest.raises(ValidationError):
        bd.s = 0.9  # type: ignore[misc]
    with pytest.raises(ValidationError):
        ComponentBreakdown(
            s=0.0,
            m=0.0,
            e=0.0,
            f=0.0,
            h=0.0,
            static_terms=_STATIC,
            meteo_terms=_METEO,
            componente_inventata=1.0,  # type: ignore[call-arg]
        )


# ---------------------------------------------------------------------------
# Un secondo hazard, definito solo qui: nessun file di produzione lo conosce.
# ---------------------------------------------------------------------------
class _FakeFloodBreakdown(HazardBreakdown):
    hazard_type: Literal[HazardType.FLOOD] = HazardType.FLOOD
    depth_norm: float = Field(..., ge=0.0, le=1.0)


class _FakeFloodEngine:
    """Motore fittizio con la firma del Protocol e un breakdown proprio."""

    def score(self, bundle: CellFeatureBundle) -> RiskScore[_FakeFloodBreakdown]:
        return RiskScore(
            score=0.7,
            level=RiskLevel.High,
            breakdown=_FakeFloodBreakdown(depth_norm=0.9),
            model_version="fake-flood",
        )


def _bundle() -> CellFeatureBundle:
    return CellFeatureBundle(
        aoi_id="aoi-test",
        cell_id="cell-test",
        static=StaticFactors(cell_id="cell-test"),
        dynamic=DynamicInputs(valuation_time=datetime(2026, 6, 1, tzinfo=UTC)),
    )


def test_a_second_hazard_needs_no_production_change() -> None:
    """Il criterio di accettazione di #57: registrare un motore fittizio non
    richiede modifiche fuori da registry e config."""
    scored = _FakeFloodEngine().score(_bundle())
    assert scored.breakdown.hazard_type is HazardType.FLOOD
    assert scored.to_dict()["breakdown"] == {"hazard_type": "flood", "depth_norm": 0.9}


def _read_only_the_discriminator(engine: ScoringEngine[HazardBreakdown]) -> HazardType:
    """Ciò che farà il registry: tiene motori di hazard diversi dietro un tipo."""
    return engine.score(_bundle()).breakdown.hazard_type


def test_engines_of_different_hazards_share_one_type() -> None:
    """La covarianza del parametro è ciò che rende possibile il registry.

    Se `RiskScore` fosse invariante, un motore frane non sarebbe assegnabile
    a `ScoringEngine[HazardBreakdown]` e il registry di #84 non potrebbe
    tenere insieme motori di hazard diversi. mypy lo verifica staticamente;
    qui si verifica che a runtime il discriminante sia leggibile da entrambi.
    """
    from limen.core.scoring.engine import MultiFactorScoringEngine

    assert _read_only_the_discriminator(MultiFactorScoringEngine()) is DEFAULT_HAZARD
    assert _read_only_the_discriminator(_FakeFloodEngine()) is HazardType.FLOOD
