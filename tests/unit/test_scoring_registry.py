"""Registry bidimensionale hazard x implementazione (issue #84).

Il criterio di accettazione centrale di #57 vive qui: **registrare un motore
per un pericolo nuovo non deve richiedere modifiche fuori da registry e
config**. Il test lo dimostra registrando un motore fittizio per `flood` e
risolvendolo, senza che nessun file di produzione lo conosca.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Literal

import pytest

from limen.config.settings import ScoringEngineKind, ScoringMode, Settings
from limen.core.models.hazard import DEFAULT_HAZARD, HazardType
from limen.core.models.risk import (
    CellFeatureBundle,
    ComponentBreakdown,
    DynamicInputs,
    HazardBreakdown,
    RiskLevel,
    RiskScore,
    StaticFactors,
)
from limen.core.scoring.engine import MultiFactorScoringEngine
from limen.core.scoring.regional_thresholds import (
    RegionalThresholds,
    load_hazard_thresholds,
    load_regional_thresholds,
)
from limen.core.scoring.registry import (
    EngineNotRegisteredError,
    is_registered,
    register,
    registered_hazards,
    registered_pairs,
    resolve,
    unregister,
)
from limen.core.scoring.resolver import resolve_challenger, resolve_scoring_engine


def _bundle() -> CellFeatureBundle:
    return CellFeatureBundle(
        aoi_id="aoi-test",
        cell_id="cell-test",
        static=StaticFactors(cell_id="cell-test"),
        dynamic=DynamicInputs(valuation_time=datetime(2026, 6, 1, tzinfo=UTC)),
    )


# ---------------------------------------------------------------------------
# Le registrazioni di serie
# ---------------------------------------------------------------------------
def test_landslide_is_registered_on_both_axes() -> None:
    assert is_registered(HazardType.LANDSLIDE, ScoringEngineKind.DETERMINISTIC)
    assert is_registered(HazardType.LANDSLIDE, ScoringEngineKind.ML)
    assert registered_hazards() >= {HazardType.LANDSLIDE}


def test_resolve_returns_the_v1_engine() -> None:
    engine = resolve(HazardType.LANDSLIDE, ScoringEngineKind.DETERMINISTIC)
    assert isinstance(engine, MultiFactorScoringEngine)


def test_unregistered_pair_fails_loudly_and_says_what_exists() -> None:
    """Un pericolo scritto male in configurazione deve rompere subito e a voce
    alta, non valutare silenziosamente zero celle."""
    with pytest.raises(EngineNotRegisteredError) as exc:
        resolve(HazardType.FLOOD, ScoringEngineKind.DETERMINISTIC)
    message = str(exc.value)
    assert "flood/deterministic" in message
    # L'errore elenca cosa c'è, così chi legge il log capisce cosa manca.
    assert "landslide/deterministic" in message


def test_double_registration_is_refused() -> None:
    """Una sovrascrittura silenziosa renderebbe il champion dipendente
    dall'ordine di import dei moduli."""
    with pytest.raises(ValueError, match="already registered"):
        register(
            HazardType.LANDSLIDE,
            ScoringEngineKind.DETERMINISTIC,
            lambda _s, _t: MultiFactorScoringEngine(),
            breakdown=ComponentBreakdown,
        )


def test_thresholds_override_reaches_the_engine() -> None:
    """`AppDependencies` e i test iniettano una configurazione senza scriverla
    su disco: l'override deve arrivare al motore, non essere ignorato."""
    custom = load_regional_thresholds()
    engine = resolve(HazardType.LANDSLIDE, ScoringEngineKind.DETERMINISTIC, thresholds=custom)
    scored = engine.score(_bundle())
    assert scored.model_version == custom.model_version


# ---------------------------------------------------------------------------
# Un pericolo nuovo: nessun file di produzione lo conosce
# ---------------------------------------------------------------------------
class _FakeFloodBreakdown(HazardBreakdown):
    hazard_type: Literal[HazardType.FLOOD] = HazardType.FLOOD
    depth_norm: float


class _FakeFloodEngine:
    def score(self, bundle: CellFeatureBundle) -> RiskScore[_FakeFloodBreakdown]:
        return RiskScore(
            score=0.66,
            level=RiskLevel.High,
            breakdown=_FakeFloodBreakdown(depth_norm=0.8),
            model_version="fake-flood-v1",
        )


@pytest.fixture()
def fake_flood_registered() -> Iterator[None]:
    register(
        HazardType.FLOOD,
        ScoringEngineKind.DETERMINISTIC,
        lambda _s, _t: _FakeFloodEngine(),
        breakdown=_FakeFloodBreakdown,
    )
    yield
    unregister(HazardType.FLOOD, ScoringEngineKind.DETERMINISTIC)


def test_a_new_hazard_only_needs_a_registration(fake_flood_registered: None) -> None:
    """Criterio di accettazione di #57."""
    assert HazardType.FLOOD in registered_hazards()
    engine = resolve(HazardType.FLOOD, ScoringEngineKind.DETERMINISTIC)
    scored = engine.score(_bundle())
    assert scored.breakdown.hazard_type is HazardType.FLOOD
    assert scored.model_version == "fake-flood-v1"


def test_registration_round_trip_leaves_no_residue() -> None:
    """Il registry è stato globale di processo: una registrazione dimenticata
    falserebbe ogni test successivo della sessione. Indipendente dall'ordine,
    perché registra e ripulisce da sé."""
    key = (HazardType.FLOOD, ScoringEngineKind.DETERMINISTIC)
    assert not is_registered(*key)
    register(*key, lambda _s, _t: _FakeFloodEngine(), breakdown=_FakeFloodBreakdown)
    try:
        assert is_registered(*key)
        assert key in registered_pairs()
    finally:
        unregister(*key)
    assert not is_registered(*key)
    assert key not in registered_pairs()


# ---------------------------------------------------------------------------
# Il resolver: politica operativa sopra il registry
# ---------------------------------------------------------------------------
def test_resolver_defaults_to_the_deterministic_engine() -> None:
    s = Settings.model_validate({"scoring": {"engine": "deterministic"}})
    assert isinstance(resolve_scoring_engine(settings=s), MultiFactorScoringEngine)


def test_resolver_degrades_to_v1_when_ml_cannot_load() -> None:
    """Il baseline deterministico resta un fallback vivo: senza modello
    promosso o senza il gruppo `ml` installato, lo sweep continua."""
    s = Settings.model_validate({"scoring": {"engine": "ml"}})
    engine = resolve_scoring_engine(settings=s)
    assert isinstance(engine, MultiFactorScoringEngine)


def test_no_challenger_outside_shadow_mode() -> None:
    s = Settings.model_validate({"scoring": {"mode": ScoringMode.CHAMPION_ONLY.value}})
    assert resolve_challenger(settings=s) is None


def test_challenger_is_the_other_implementation() -> None:
    """Champion ML ⇒ il challenger naturale è il V1 deterministico."""
    s = Settings.model_validate({"scoring": {"engine": "ml", "mode": ScoringMode.SHADOW.value}})
    assert isinstance(resolve_challenger(settings=s), MultiFactorScoringEngine)


# ---------------------------------------------------------------------------
# Config per pericolo
# ---------------------------------------------------------------------------
def test_landslide_yaml_is_unchanged_by_the_move() -> None:
    """Il file è passato da config/regional_thresholds.yaml a
    config/hazards/landslide.yaml: l'oggetto caricato deve essere identico,
    altrimenti ogni punteggio cambierebbe."""
    assert load_hazard_thresholds(HazardType.LANDSLIDE).model_dump() == (
        load_regional_thresholds().model_dump()
    )


def test_default_hazard_is_the_wrapper_target() -> None:
    assert (
        load_hazard_thresholds(DEFAULT_HAZARD).model_dump()
        == load_regional_thresholds().model_dump()
    )


def test_cache_is_keyed_per_hazard() -> None:
    """Due pericoli non devono condividere una configurazione già interpretata."""
    first = load_hazard_thresholds(HazardType.LANDSLIDE)
    second = load_hazard_thresholds(HazardType.LANDSLIDE)
    # Stesso pericolo ⇒ stesso oggetto in cache.
    assert first is second
    # Pericoli diversi ⇒ configurazioni diverse, non la stessa riusata.
    assert load_hazard_thresholds(HazardType.WILDFIRE) is not first
    # Un pericolo senza file non deve restituire quello delle frane.
    with pytest.raises(FileNotFoundError):
        load_hazard_thresholds(HazardType.FLOOD)


def test_explicit_path_bypasses_the_cache() -> None:
    """I test scambiano configurazione passando un percorso: quella via non
    deve inquinare la cache del pericolo."""
    from limen.core.scoring.regional_thresholds import hazard_thresholds_path

    packaged = hazard_thresholds_path(HazardType.LANDSLIDE)
    loaded: RegionalThresholds = load_hazard_thresholds(HazardType.LANDSLIDE, path=packaged)
    assert loaded is not load_hazard_thresholds(HazardType.LANDSLIDE)
    assert loaded.model_dump() == load_hazard_thresholds(HazardType.LANDSLIDE).model_dump()


def test_component_breakdown_survives_the_registry_round_trip() -> None:
    """Il motore risolto dal registry produce ancora il breakdown frane."""
    engine = resolve(HazardType.LANDSLIDE, ScoringEngineKind.DETERMINISTIC)
    scored = engine.score(_bundle())
    assert isinstance(scored.breakdown, ComponentBreakdown)
    assert scored.breakdown.hazard_type is HazardType.LANDSLIDE


# ---------------------------------------------------------------------------
# Difetti trovati in revisione (#84)
# ---------------------------------------------------------------------------
def test_injected_settings_reach_the_ml_factory() -> None:
    """La factory non deve leggere i Settings globali.

    Il motore ML prende da lì le coordinate MLflow: pescare le globali
    scarterebbe in silenzio una configurazione iniettata, ed è così che un
    test puntato a un registry inesistente finisce per passare per il motivo
    sbagliato.
    """
    seen: list[Settings | None] = []

    def _spy(settings: Settings | None, _thresholds: object) -> MultiFactorScoringEngine:
        seen.append(settings)
        return MultiFactorScoringEngine()

    key = (HazardType.FLOOD, ScoringEngineKind.ML)
    register(*key, _spy, breakdown=ComponentBreakdown)
    try:
        injected = Settings.model_validate(
            {"scoring": {"mlflow_tracking_uri": "file:///tmp/limen-iniettato"}}
        )
        resolve(*key, settings=injected)
    finally:
        unregister(*key)

    assert seen and seen[0] is injected
    assert seen[0].scoring.mlflow_tracking_uri == "file:///tmp/limen-iniettato"


def test_an_unregistered_hazard_is_refused_at_build_time() -> None:
    """Valutare una cella di alluvione con le soglie di versante darebbe
    numeri sbagliati presentati come giusti: peggio di un errore rumoroso."""
    from limen.core.scoring.resolver import HazardNotScorableError, resolve_scoring_engine

    # Il primo ostacolo che il resolver incontra per un pericolo mai
    # configurato è il file di soglie: senza quello non c'è numero corretto da
    # produrre, con o senza motore registrato.
    with pytest.raises(HazardNotScorableError, match="no thresholds file"):
        resolve_scoring_engine(hazard=HazardType.FLOOD)


def test_an_engine_with_its_own_breakdown_resolves() -> None:
    """Nessun vincolo sulla forma del breakdown, dalla Fase 2.

    Prima il resolver rifiutava un motore che non producesse i componenti
    delle frane, perché `CellRiskRecord` li leggeva per nome; ora il record
    porta il breakdown del pericolo e i consumatori lo interrogano tramite le
    proiezioni. Il vincolo era la ragione per cui un secondo pericolo non
    poteva girare nel workflow.
    """
    from limen.core.scoring.resolver import resolve_scoring_engine

    key = (HazardType.FLOOD, ScoringEngineKind.DETERMINISTIC)
    register(*key, lambda _s, _t: _FakeFloodEngine(), breakdown=_FakeFloodBreakdown)
    try:
        assert isinstance(resolve_scoring_engine(hazard=HazardType.FLOOD), _FakeFloodEngine)
    finally:
        unregister(*key)


def test_an_engine_reusing_the_landslide_breakdown_is_accepted() -> None:
    """Un motore che riusa la forma dei componenti delle frane resta valido:
    la forma non è più un vincolo, ma neanche un divieto."""
    key = (HazardType.FLOOD, ScoringEngineKind.DETERMINISTIC)
    register(
        *key,
        lambda _s, t: MultiFactorScoringEngine(t or load_regional_thresholds()),
        breakdown=ComponentBreakdown,
    )
    try:
        engine = resolve_scoring_engine(hazard=HazardType.FLOOD)
        assert isinstance(engine, MultiFactorScoringEngine)
    finally:
        unregister(*key)


def test_check_scorable_catches_a_misconfigured_hazard() -> None:
    """Chiamata all'avvio su ogni voce di HAZARDS__ENABLED, così un errore di
    battitura si vede al boot e non come AttributeError a metà sweep."""
    from limen.core.scoring.resolver import HazardNotScorableError, check_scorable

    check_scorable(HazardType.LANDSLIDE)

    with pytest.raises(HazardNotScorableError, match="no deterministic engine"):
        check_scorable(HazardType.FLOOD)

    # Motore registrato ma senza file di soglie: va colto comunque.
    key = (HazardType.FLOOD, ScoringEngineKind.DETERMINISTIC)
    register(*key, lambda _s, _t: _FakeFloodEngine(), breakdown=_FakeFloodBreakdown)
    try:
        with pytest.raises(HazardNotScorableError, match="no thresholds file"):
            check_scorable(HazardType.FLOOD)
    finally:
        unregister(*key)
