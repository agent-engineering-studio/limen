"""Workflow MAF parametrico per pericolo (issue #85).

Due proprietà. Con un solo pericolo abilitato la forma del workflow è quella
di prima, passo per passo: è ciò che rende il refactor invisibile. E un
pericolo che non si può valutare viene rifiutato **al build**, non a metà
sweep, dove sarebbe un `AttributeError` dentro un executor.
"""

from __future__ import annotations

import pytest

from limen.agents.llm_factory.stub import StubLlmClientFactory
from limen.agents.workflows.main_workflow import (
    WorkflowDeps,
    build_hazard_workflow,
    build_landslide_workflow,
)
from limen.config.settings import ScoringEngineKind, Settings
from limen.core.models.hazard import DEFAULT_HAZARD, HazardType
from limen.core.models.risk import ComponentBreakdown
from limen.core.scoring.engine import MultiFactorScoringEngine
from limen.core.scoring.regional_thresholds import load_regional_thresholds
from limen.core.scoring.registry import _REGISTRY, register, unregister
from limen.core.scoring.resolver import HazardNotScorableError, check_scorable


def _deps(**overrides: object) -> WorkflowDeps:
    return WorkflowDeps(
        llm_factory=StubLlmClientFactory(),
        settings=Settings.model_validate(overrides or {}),
    )


def test_landslide_workflow_shape_is_unchanged() -> None:
    """L'alias e la funzione parametrica producono lo stesso workflow.

    Se il conteggio dei passi cambiasse, qualcosa sarebbe entrato o uscito
    dalla pipeline senza che nessuno l'abbia deciso.
    """
    alias = build_landslide_workflow(_deps())
    explicit = build_hazard_workflow(DEFAULT_HAZARD, _deps())
    assert alias.step_count == explicit.step_count


def test_workflow_name_carries_the_hazard() -> None:
    """Il nome finisce nei log di ogni passo: senza il pericolo, con due
    pericoli attivi non si distinguerebbe quale sweep sta parlando."""
    wf = build_hazard_workflow(DEFAULT_HAZARD, _deps())
    assert wf.name == "limen-landslide-v1"


def test_a_hazard_with_no_engine_is_refused_at_build_time() -> None:
    """Non a metà sweep: lì sarebbe una riga di log fra migliaia.

    L'ordine dei controlli segue quello in cui si sistemano le cose:
    registrazione, poi file di soglie, poi compatibilità del breakdown. Il
    messaggio nomina il primo ostacolo, non l'ultimo.
    """
    with pytest.raises(HazardNotScorableError, match="no deterministic engine registered"):
        build_hazard_workflow(HazardType.FLOOD, _deps())


def test_an_unreadable_breakdown_is_refused_at_build_time() -> None:
    """Il controllo è sulla forma del breakdown, non sul nome del pericolo.

    Esercitato su `landslide`, l'unico pericolo con un file di soglie in Fase
    1, sostituendone la registrazione: è l'unico modo di arrivare al terzo
    controllo passando per i due precedenti.
    """
    from limen.core.models.risk import HazardBreakdown

    class _OtherShape(HazardBreakdown):
        hazard_type: HazardType = DEFAULT_HAZARD

    key = (DEFAULT_HAZARD, ScoringEngineKind.DETERMINISTIC)
    # Snapshot dell'entry vera, non solo del breakdown: il registry è stato
    # globale di processo, e rimettere al suo posto una lambda equivalente
    # lascerebbe i test successivi a girare su una factory diversa da quella
    # di produzione.
    original = _REGISTRY[key]
    register(
        *key,
        original.factory,
        breakdown=_OtherShape,
        replace=True,
    )
    try:
        with pytest.raises(HazardNotScorableError, match="reads landslide components"):
            build_hazard_workflow(DEFAULT_HAZARD, _deps())
    finally:
        _REGISTRY[key] = original


def test_a_hazard_without_its_yaml_is_refused_at_build_time() -> None:
    """In Fase 1 esiste solo `hazards/landslide.yaml`. Registrare un motore
    flood non basta: gli executor caricano le soglie di quel pericolo, e senza
    quel file il build deve dirlo con un messaggio che nomina il file atteso,
    non lasciar passare un FileNotFoundError da dentro un executor.

    I file degli altri pericoli arrivano con #61 (wildfire) e #63 (flood):
    #84 ha rifiutato di proposito un file di blocchi condivisi, quindi ogni
    pericolo ha bisogno della sua configurazione completa.
    """
    key = (HazardType.FLOOD, ScoringEngineKind.DETERMINISTIC)
    register(
        *key,
        lambda _s, t: MultiFactorScoringEngine(t or load_regional_thresholds()),
        breakdown=ComponentBreakdown,
    )
    try:
        with pytest.raises(HazardNotScorableError, match="no thresholds file"):
            build_hazard_workflow(HazardType.FLOOD, _deps())
    finally:
        unregister(*key)


def test_the_check_runs_even_with_an_injected_engine() -> None:
    """Iniettare il motore non salta il controllo: gli executor caricano
    comunque le soglie del pericolo, quindi un pericolo senza YAML resta non
    valutabile anche se il chiamante porta il proprio motore."""
    deps = WorkflowDeps(
        llm_factory=StubLlmClientFactory(),
        settings=Settings.model_validate({}),
        scoring_engine=MultiFactorScoringEngine(load_regional_thresholds()),
    )
    with pytest.raises(HazardNotScorableError):
        build_hazard_workflow(HazardType.FLOOD, deps)


# ---------------------------------------------------------------------------
# Difetti trovati in revisione (#85)
# ---------------------------------------------------------------------------
def test_ml_configured_but_unregistered_degrades_to_v1() -> None:
    """L'invariante «V1 resta il baseline» non ammette eccezioni.

    Con `SCORING__ENGINE=ml` su un pericolo che offre solo il motore
    deterministico, il resolver deve degradare, non sollevare: un pericolo
    non registrato è qualcosa attorno a cui si degrada, mentre solo un motore
    registrato con la forma sbagliata è fatale.
    """
    from limen.core.scoring.resolver import resolve_scoring_engine

    key = (DEFAULT_HAZARD, ScoringEngineKind.ML)
    saved = _REGISTRY.pop(key)
    try:
        s = Settings.model_validate({"scoring": {"engine": "ml"}})
        check_scorable(DEFAULT_HAZARD, s.scoring.engine)
        assert isinstance(resolve_scoring_engine(settings=s), MultiFactorScoringEngine)
    finally:
        _REGISTRY[key] = saved


def test_the_fallback_prefers_the_hazard_own_deterministic_engine() -> None:
    """Degradare non vuol dire ricadere sulla formula generica.

    Un pericolo con un proprio motore deterministico registrato deve ricevere
    *quello*, non una costruzione diretta che ignora la registrazione.
    """
    from limen.core.scoring.resolver import resolve_scoring_engine

    built: list[str] = []

    class _OwnEngine(MultiFactorScoringEngine):
        pass

    def _own(_s: object, t: object) -> _OwnEngine:
        built.append("own")
        return _OwnEngine(t or load_regional_thresholds())  # type: ignore[arg-type]

    key = (DEFAULT_HAZARD, ScoringEngineKind.DETERMINISTIC)
    saved = _REGISTRY[key]
    register(*key, _own, breakdown=ComponentBreakdown, replace=True)
    try:
        s = Settings.model_validate({"scoring": {"engine": "ml"}})
        # ML non caricabile in questo ambiente ⇒ fallback.
        engine = resolve_scoring_engine(settings=s)
        assert isinstance(engine, _OwnEngine)
        assert built == ["own"]
    finally:
        _REGISTRY[key] = saved


def test_alert_summary_names_the_hazard() -> None:
    """Con due pericoli attivi arrivano due alert per AOI: se il testo non
    dice quale, il destinatario non li distingue."""
    from datetime import UTC, datetime

    from limen.config.settings import AlertSettings
    from limen.core.models.context import AggregateAssessment
    from limen.notifications.base import build_alert_payload

    assessment = AggregateAssessment(
        aoi_id="aoi-test",
        hazard_type=HazardType.FLOOD,
        model_version="test",
        valuation_time=datetime(2026, 6, 1, tzinfo=UTC),
        n_cells=1,
        cells_high_or_above=1,
        cells_by_level={"High": 1},
    )
    payload = build_alert_payload(
        assessment=assessment,
        prioritised=[],
        settings=AlertSettings(),
        dispatched_at=datetime(2026, 6, 1, tzinfo=UTC),
    )
    assert payload.hazard_type is HazardType.FLOOD
    assert "alluvione" in payload.summary_it
