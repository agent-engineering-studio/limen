"""I tre profili di cadenza del workflow (#78).

Il profilo non è una preferenza: è quali nodi girano. L'orario deve stare
dentro il tick, e la misura del passo 1 dell'epic #74 dice dov'era finito il
tempo su una regione da 10.353 celle — RiskAnalyst 102,0 s, Briefing 38,3 s,
PersistResult 13,2 s, RiskScoring 0,88 s. I due nodi dichiarati "non
autoritativi" costavano il 90% dello sweep.

I nomi dei nodi e non solo il conteggio: un profilo che toglie i due nodi LLM
e ne reintroduce uno per sbaglio ha lo stesso `step_count` di uno corretto.
"""

from __future__ import annotations

import pytest

from limen.agents.llm_factory.stub import StubLlmClientFactory
from limen.agents.workflows.main_workflow import (
    WorkflowDeps,
    build_hazard_workflow,
    level_reached,
)
from limen.config.settings import Settings
from limen.core.models.hazard import DEFAULT_HAZARD

_LLM_NODES = {"RiskAnalyst", "Briefing"}


def _deps(**overrides: object) -> WorkflowDeps:
    return WorkflowDeps(
        llm_factory=StubLlmClientFactory(),
        settings=Settings.model_validate(overrides or {}),
    )


def test_the_hourly_profile_has_no_llm_node() -> None:
    wf = build_hazard_workflow(DEFAULT_HAZARD, _deps(), profile="hourly")
    assert _LLM_NODES.isdisjoint(wf.step_names)


def test_the_hourly_profile_still_persists_and_alerts() -> None:
    """Togliere la narrativa non deve togliere l'operatività: l'orario è
    l'unico percorso che scrive la mappa e manda le allerte."""
    names = build_hazard_workflow(DEFAULT_HAZARD, _deps(), profile="hourly").step_names
    assert "PersistResult" in names
    assert "AlertDispatch" in names
    assert "RiskScoring" in names


def test_the_default_profile_keeps_the_narrative() -> None:
    """Il default resta `forecast`: `monitor-once`, MCP e i test esistenti non
    devono perdere la prosa perché lo sweep orario ne ha fatto a meno."""
    names = build_hazard_workflow(DEFAULT_HAZARD, _deps()).step_names
    assert _LLM_NODES.issubset(names)


def test_the_hourly_profile_has_no_shadow_even_in_shadow_mode() -> None:
    """`SCORING__MODE=shadow` continua a significare "il challenger esiste",
    ma LightGBM più SHAP per cella ogni ora è il costo di un modello che il
    verdetto shadow dà già per non promuovibile con queste feature."""
    deps = _deps(scoring={"mode": "shadow"})
    hourly = build_hazard_workflow(DEFAULT_HAZARD, deps, profile="hourly")
    assert "ShadowChallenger" not in hourly.step_names


def test_the_nightly_profile_neither_persists_nor_alerts() -> None:
    """Il notturno misura, non opera. Persistere darebbe alla mappa due
    valutazioni dello stesso giorno con la stessa dignità, e dispacciare
    allerte alle due di notte su un modello non promosso sarebbe peggio."""
    names = build_hazard_workflow(DEFAULT_HAZARD, _deps(), profile="nightly").step_names
    assert "PersistResult" not in names
    assert "AlertDispatch" not in names
    assert "RiskScoring" in names


@pytest.mark.parametrize(
    ("counts", "min_level", "expected"),
    [
        ({"Low": 10}, "Moderate", False),
        ({"Low": 10, "Moderate": 1}, "Moderate", True),
        ({"VeryHigh": 1}, "High", True),
        ({}, "None", True),
        ({"None": 5}, "Low", False),
    ],
)
def test_level_reached_is_the_same_gate_the_workflow_used(
    counts: dict[str, int], min_level: str, expected: bool
) -> None:
    """Il briefing asincrono deve decidere con la stessa soglia del nodo LLM:
    due copie della regola sarebbero divergite alla prima taratura."""
    assert level_reached(counts, min_level) is expected
