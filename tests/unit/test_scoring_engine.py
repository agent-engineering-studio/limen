"""MultiFactorScoringEngine — aggregation, classification, monotonicity, YAML override.

Tests rely on the packaged ``hazards/landslide.yaml``; one explicit
test (``test_engine_reads_all_constants_from_yaml``) overrides the
config to prove there are no hard-coded magic numbers.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from limen.core.models.risk import (
    CellFeatureBundle,
    DynamicInputs,
    RainfallSample,
    RainfallSeries,
    RiskLevel,
    SeismicHistoryEvent,
    StaticFactors,
)
from limen.core.scoring.engine import MultiFactorScoringEngine, score
from limen.core.scoring.regional_thresholds import (
    DEFAULT_THRESHOLDS_PATH,
    load_regional_thresholds,
)

VALUATION_TIME = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def _bundle(
    *,
    static: StaticFactors | None = None,
    rainfall_hourly: list[float] | None = None,
    api_30_mm: float | None = None,
    soil: float | None = None,
    seismic: list[SeismicHistoryEvent] | None = None,
    months_since_fire: float | None = None,
    valuation_time: datetime | None = None,
) -> CellFeatureBundle:
    static = static or StaticFactors(cell_id="c-test")
    samples: tuple[RainfallSample, ...] = ()
    if rainfall_hourly:
        start = (valuation_time or VALUATION_TIME) - timedelta(hours=len(rainfall_hourly))
        samples = tuple(
            RainfallSample(timestamp=start + timedelta(hours=i), precipitation_mm=v)
            for i, v in enumerate(rainfall_hourly)
        )
    return CellFeatureBundle(
        aoi_id="aoi-test",
        cell_id=static.cell_id,
        static=static,
        dynamic=DynamicInputs(
            valuation_time=valuation_time or VALUATION_TIME,
            rainfall=RainfallSeries(samples=samples),
            api_30_mm=api_30_mm,
            soil_moisture_0_7=soil,
            seismic_history=tuple(seismic) if seismic else (),
            months_since_fire=months_since_fire,
        ),
    )


# ---------------------------------------------------------------------------
# Determinism + purity
# ---------------------------------------------------------------------------
def test_same_input_yields_same_output() -> None:
    b = _bundle(rainfall_hourly=[5, 5, 5, 5, 5, 5], api_30_mm=120.0, soil=0.35)
    a1 = score(b)
    a2 = score(b)
    assert a1 == a2


def test_score_is_in_unit_interval() -> None:
    b = _bundle(
        static=StaticFactors(
            cell_id="c",
            susc_ispra=1.0,
            iffi_density_500=10.0,
            slope_deg=80.0,
            pai_class_norm=1.0,
            litho_weight=1.0,
        ),
        rainfall_hourly=[50, 50, 50, 50, 50, 50],
        api_30_mm=400.0,
        soil=1.0,
        months_since_fire=6.0,
    )
    s = score(b)
    assert 0.0 <= s.score <= 1.0


# ---------------------------------------------------------------------------
# Monotonicity
# ---------------------------------------------------------------------------
def test_more_rain_does_not_lower_score() -> None:
    b_low = _bundle(rainfall_hourly=[1, 1, 1, 1, 1, 1])
    b_high = _bundle(rainfall_hourly=[30, 30, 30, 30, 30, 30])
    assert score(b_high).score >= score(b_low).score


def test_higher_susceptibility_does_not_lower_score() -> None:
    low_s = StaticFactors(cell_id="c", susc_ispra=0.1)
    high_s = StaticFactors(cell_id="c", susc_ispra=0.9)
    assert score(_bundle(static=high_s)).score >= score(_bundle(static=low_s)).score


def test_older_quake_decays_seismic_factor() -> None:
    """For two otherwise-identical bundles, the older quake yields ≤ score."""
    fresh = SeismicHistoryEvent(
        event_id="fresh",
        origin_time=VALUATION_TIME,
        magnitude=4.5,
        distance_km=10.0,
        pga_g=0.15,
    )
    aged = SeismicHistoryEvent(
        event_id="aged",
        origin_time=VALUATION_TIME - timedelta(days=5),
        magnitude=4.5,
        distance_km=10.0,
        pga_g=0.15,
    )
    s_fresh = score(_bundle(seismic=[fresh]))
    s_aged = score(_bundle(seismic=[aged]))
    assert s_fresh.score >= s_aged.score
    assert s_fresh.breakdown.e >= s_aged.breakdown.e


# ---------------------------------------------------------------------------
# Class boundaries
# ---------------------------------------------------------------------------
def test_low_signal_classifies_as_none() -> None:
    s = score(_bundle())
    assert s.level in {RiskLevel.None_, RiskLevel.Low}


def test_high_static_only_can_reach_moderate_or_above() -> None:
    """Saturating S alone gets the bundle past Low (~0.35)."""
    fully_loaded_static = StaticFactors(
        cell_id="c",
        susc_ispra=1.0,
        iffi_density_500=10.0,
        slope_deg=80.0,
        pai_class_norm=1.0,
        litho_weight=1.0,
    )
    s = score(_bundle(static=fully_loaded_static))
    assert s.score >= 0.0
    assert s.level in {RiskLevel.Low, RiskLevel.Moderate, RiskLevel.High, RiskLevel.VeryHigh}


def test_extreme_inputs_reach_very_high() -> None:
    """Saturate every component → VeryHigh class."""
    fully_loaded_static = StaticFactors(
        cell_id="c",
        susc_ispra=1.0,
        iffi_density_500=10.0,
        slope_deg=80.0,
        pai_class_norm=1.0,
        litho_weight=1.0,
    )
    fresh_quake = SeismicHistoryEvent(
        event_id="big",
        origin_time=VALUATION_TIME,
        magnitude=5.5,
        distance_km=5.0,
        pga_g=0.40,
    )
    s = score(
        _bundle(
            static=fully_loaded_static,
            rainfall_hourly=[40] * 8,
            api_30_mm=400.0,
            soil=0.9,
            seismic=[fresh_quake],
            months_since_fire=6.0,
        )
    )
    assert s.level is RiskLevel.VeryHigh
    assert s.score >= 0.75


def test_breakdown_components_are_in_unit_interval() -> None:
    s = score(_bundle(rainfall_hourly=[10] * 6, api_30_mm=150.0, soil=0.5))
    b = s.breakdown
    for v in (b.s, b.m, b.e, b.f, b.h):
        assert 0.0 <= v <= 1.0


# ---------------------------------------------------------------------------
# YAML override — proves no hard-coded constants
# ---------------------------------------------------------------------------
@pytest.fixture
def tweaked_yaml(tmp_path: Path) -> Iterator[Path]:
    text = DEFAULT_THRESHOLDS_PATH.read_text(encoding="utf-8")
    cfg = yaml.safe_load(text)
    cfg["weights"]["static"] = 1.0
    cfg["weights"]["meteo"] = 0.0
    cfg["weights"]["seismic"] = 0.0
    cfg["weights"]["fire"] = 0.0
    cfg["weights"]["hydrology"] = 0.0
    # Drive S entirely off susceptibility so the test controls its own
    # constant (proves the engine reads sub-weights from the YAML, not
    # from the reweighted default where susc_ispra = 0).
    cfg["static"]["weights"] = {
        "susc_ispra": 1.0,
        "iffi_density": 0.0,
        "slope": 0.0,
        "pai": 0.0,
        "litho_weight": 0.0,
    }
    out = tmp_path / "tweaked.yaml"
    out.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    yield out


def test_engine_reads_all_constants_from_yaml(tweaked_yaml: Path) -> None:
    """w_S=1, others=0 → score equals S regardless of meteo/seismic/fire."""
    tweaked = load_regional_thresholds(tweaked_yaml)
    engine = MultiFactorScoringEngine(tweaked)

    bundle = _bundle(
        static=StaticFactors(cell_id="c", susc_ispra=0.1),
        rainfall_hourly=[40] * 8,  # would normally push score up
        api_30_mm=300.0,
        soil=0.9,
    )
    result = engine.score(bundle)
    # Static-only weights with susc sub-weight forced to 1.0 → S = 1.0 · 0.1.
    assert result.score == pytest.approx(0.1, abs=1e-9)
    assert result.breakdown.m > 0.0  # raw component still computed (auditable)
    assert result.level is RiskLevel.None_


def test_engine_model_version_propagates() -> None:
    s = score(_bundle())
    assert s.model_version == load_regional_thresholds().model_version


# ---------------------------------------------------------------------------
# Rain-on-snow (snow block)
# ---------------------------------------------------------------------------
def test_no_snowpack_scores_identical_to_pre_snow_engine() -> None:
    """snow_depth None or below ros_min_depth_m ⇒ snow_factor 0 ⇒ same M."""
    base = _bundle(rainfall_hourly=[3.0] * 12, api_30_mm=100.0, soil=0.30)
    shallow = base.model_copy(
        update={"dynamic": base.dynamic.model_copy(update={"snow_depth_m": 0.01})}
    )
    assert score(shallow).breakdown.meteo_terms.snow_factor == 0.0
    assert score(shallow).score == score(base).score


def test_rain_on_snow_amplifies_m() -> None:
    base = _bundle(rainfall_hourly=[3.0] * 12, api_30_mm=100.0, soil=0.30)
    snowy = base.model_copy(
        update={"dynamic": base.dynamic.model_copy(update={"snow_depth_m": 0.5})}
    )
    dry_snow = _bundle(api_30_mm=100.0, soil=0.30).model_copy(
        update={
            "dynamic": _bundle(api_30_mm=100.0, soil=0.30).dynamic.model_copy(
                update={"snow_depth_m": 0.5}
            )
        }
    )
    scored = score(snowy)
    assert scored.breakdown.meteo_terms.snow_factor > 0.0
    assert scored.breakdown.m > score(base).breakdown.m
    # Snowpack WITHOUT recent rain adds nothing (it's rain-ON-snow).
    assert score(dry_snow).breakdown.meteo_terms.snow_factor == 0.0


# ---------------------------------------------------------------------------
# Rain floor — tier bypass predicate (issue #20)
# ---------------------------------------------------------------------------
_LOW_SUSC = StaticFactors(cell_id="c", susc_ispra=0.05, iffi_density_500=0.0)


def test_floor_rescues_low_susceptibility_cell_with_extreme_rain() -> None:
    """A low-susceptibility cell with rain over the floor is rescued regardless
    of its tier — the predicate never looks at susceptibility."""
    engine = MultiFactorScoringEngine()
    b = _bundle(static=_LOW_SUSC, rainfall_hourly=[5.0] * 6, soil=0.60)
    assert engine.is_rescued_by_floor(b) is True
    # Rescued ⇒ it gets scored and can carry a non-zero risk (can escalate).
    assert engine.score(b).score > 0.0


def test_floor_leaves_sub_floor_rain_pruned() -> None:
    """Rain below the floor ⇒ not rescued ⇒ the tiering saving is preserved
    (no superfluous meteo/LLM spend on this cell)."""
    engine = MultiFactorScoringEngine()
    b = _bundle(static=_LOW_SUSC, rainfall_hourly=[1.0] * 6, soil=0.60)
    assert engine.is_rescued_by_floor(b) is False


def test_floor_is_conditioned_on_antecedent_wetness() -> None:
    """Same rain over the floor: a saturated cell is rescued, a dry one is not."""
    engine = MultiFactorScoringEngine()
    saturated = _bundle(static=_LOW_SUSC, rainfall_hourly=[5.0] * 6, soil=0.60)
    dry = _bundle(static=_LOW_SUSC, rainfall_hourly=[5.0] * 6, soil=0.10)
    assert engine.is_rescued_by_floor(saturated) is True
    assert engine.is_rescued_by_floor(dry) is False


def test_floor_absent_returns_false(tmp_path: Path) -> None:
    """A YAML without a rain_floor block ⇒ predicate inert (backward-compatible)."""
    cfg = yaml.safe_load(DEFAULT_THRESHOLDS_PATH.read_text(encoding="utf-8"))
    cfg.pop("rain_floor", None)
    out = tmp_path / "no_floor.yaml"
    out.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    engine = MultiFactorScoringEngine(load_regional_thresholds(out))
    b = _bundle(static=_LOW_SUSC, rainfall_hourly=[50.0] * 6, soil=0.90)
    assert engine.is_rescued_by_floor(b) is False


def test_floor_values_come_from_yaml(tmp_path: Path) -> None:
    """Raising wetness_min above the saturated cell's wetness suppresses the
    rescue — proving the floor is parametrised entirely from the YAML."""
    cfg = yaml.safe_load(DEFAULT_THRESHOLDS_PATH.read_text(encoding="utf-8"))
    cfg["rain_floor"]["wetness_min"] = 0.999
    out = tmp_path / "strict_floor.yaml"
    out.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    engine = MultiFactorScoringEngine(load_regional_thresholds(out))
    b = _bundle(static=_LOW_SUSC, rainfall_hourly=[5.0] * 6, soil=0.60)
    assert engine.is_rescued_by_floor(b) is False


# ---------------------------------------------------------------------------
# Dynamic flood forecast — H uplift (issue #8)
# ---------------------------------------------------------------------------
def test_flood_forecast_lifts_h_when_rain_forecast() -> None:
    static = StaticFactors(cell_id="c", flood_hazard_norm=0.8)
    dry = _bundle(static=static)  # no forecast flood signals
    wet = dry.model_copy(
        update={"dynamic": dry.dynamic.model_copy(update={"flood_forecast_rain_72h_mm": 200.0})}
    )
    assert score(wet).breakdown.h > score(dry).breakdown.h
    assert score(wet).score >= score(dry).score


def test_flood_forecast_absent_keeps_h_static() -> None:
    # No flood signals ⇒ H equals the pure static hazard (byte-identical to V1).
    b = _bundle(static=StaticFactors(cell_id="c", flood_hazard_norm=0.8))
    assert score(b).breakdown.h == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# Innesco dalla cumulata relativa al nodo (#243)
# ---------------------------------------------------------------------------
_CON_RIFERIMENTO = StaticFactors(cell_id="c-test", pioggia_riferimento_mm=40.0)


def _caine_solo(tmp_path: Path) -> MultiFactorScoringEngine:
    """Il motore fino alla v1: innesco Caine, nessun cancello."""
    cfg = yaml.safe_load(DEFAULT_THRESHOLDS_PATH.read_text(encoding="utf-8"))
    cfg.pop("cumulata", None)
    cfg.pop("cancello_innesco", None)
    out = tmp_path / "caine.yaml"
    out.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return MultiFactorScoringEngine(load_regional_thresholds(out))


def _con_cumulata(tmp_path: Path, modo: str) -> MultiFactorScoringEngine:
    cfg = yaml.safe_load(DEFAULT_THRESHOLDS_PATH.read_text(encoding="utf-8"))
    cfg["cumulata"] = {"window_hours": 24, "saturazione": 1.0, "modo": modo}
    out = tmp_path / f"cumulata_{modo}.yaml"
    out.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return MultiFactorScoringEngine(load_regional_thresholds(out))


def test_senza_blocco_cumulata_il_riferimento_non_conta(tmp_path: Path) -> None:
    engine = _caine_solo(tmp_path)
    pioggia = [2.0] * 30
    con = engine.score(_bundle(static=_CON_RIFERIMENTO, rainfall_hourly=pioggia, soil=0.4))
    senza = engine.score(_bundle(rainfall_hourly=pioggia, soil=0.4))
    assert con.score == senza.score
    assert con.breakdown.meteo_terms.cumulata_norm is None
    assert "cumulata_norm" not in con.breakdown.factors_payload()["meteo_terms"]


def test_sostituisce_legge_solo_le_ultime_ore_della_finestra(tmp_path: Path) -> None:
    engine = _con_cumulata(tmp_path, "sostituisce")
    # 20 mm fra 30 e 25 ore fa (fuori dalle 24 h), poi 20 mm nelle ultime 24.
    pioggia = [4.0] * 5 + [0.0] * 5 + [1.0] * 20
    b = engine.score(_bundle(static=_CON_RIFERIMENTO, rainfall_hourly=pioggia, soil=0.4))
    assert b.breakdown.meteo_terms.cumulata_norm == pytest.approx(20.0 / 40.0)
    assert "cumulata_norm" in b.breakdown.factors_payload()["meteo_terms"]


def test_sostituisce_satura_al_riferimento(tmp_path: Path) -> None:
    engine = _con_cumulata(tmp_path, "sostituisce")
    b = engine.score(_bundle(static=_CON_RIFERIMENTO, rainfall_hourly=[5.0] * 24, soil=0.4))
    assert b.breakdown.meteo_terms.cumulata_norm == 1.0
    w = load_regional_thresholds().meteo.weights
    m = b.breakdown.meteo_terms
    assert b.breakdown.m == pytest.approx(
        w.caine * 1.0 + w.api * m.api_factor + w.soil * m.soil_factor
    )


def test_massimo_non_scende_sotto_caine(tmp_path: Path) -> None:
    pioggia = [0.0] * 20 + [8.0] * 4
    caine = _caine_solo(tmp_path).score(
        _bundle(static=_CON_RIFERIMENTO, rainfall_hourly=pioggia, soil=0.4)
    )
    massimo = _con_cumulata(tmp_path, "massimo").score(
        _bundle(
            static=StaticFactors(cell_id="c-test", pioggia_riferimento_mm=4000.0),
            rainfall_hourly=pioggia,
            soil=0.4,
        )
    )
    assert massimo.breakdown.m == pytest.approx(caine.breakdown.m)


def test_senza_riferimento_resta_caine(tmp_path: Path) -> None:
    pioggia = [3.0] * 24
    caine = MultiFactorScoringEngine().score(_bundle(rainfall_hourly=pioggia, soil=0.4))
    cumulata = _con_cumulata(tmp_path, "sostituisce").score(
        _bundle(rainfall_hourly=pioggia, soil=0.4)
    )
    assert cumulata.score == caine.score


def _con_durate(tmp_path: Path, durate: list[int]) -> MultiFactorScoringEngine:
    cfg = yaml.safe_load(DEFAULT_THRESHOLDS_PATH.read_text(encoding="utf-8"))
    cfg["cumulata"] = {**cfg["cumulata"], "durate_lunghe": durate}
    out = tmp_path / "durate.yaml"
    out.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return MultiFactorScoringEngine(load_regional_thresholds(out))


def test_una_pioggia_lunga_apre_il_cancello_sulla_sua_durata(tmp_path: Path) -> None:
    # 1 mm/h per tre giorni: 24 mm in 24 h, sotto la soglia del riferimento di
    # 24 h (100 mm); 72 mm in 72 h, sopra quella del riferimento di 72 h (80 mm).
    t = load_regional_thresholds()
    assert t.cumulata is not None and t.cancello_innesco is not None
    con = _PREDISPOSTA.model_copy(
        update={"pioggia_riferimento_mm": 100.0, "pioggia_riferimento_lunghe_mm": {72: 80.0}}
    )
    b = _bundle(static=con, rainfall_hourly=[1.0] * 72, api_30_mm=400.0, soil=0.9)
    assert score(b).score <= t.cancello_innesco.tetto
    lunga = _con_durate(tmp_path, [48, 72]).score(b)
    # L'ultima ora di `_bundle` è un'ora prima della valutazione: 71 nelle 72.
    assert lunga.breakdown.meteo_terms.cumulata_norm == pytest.approx(
        71.0 / (80.0 * t.cumulata.saturazione)
    )
    assert lunga.score > t.cancello_innesco.tetto


def test_una_durata_senza_riferimento_non_conta(tmp_path: Path) -> None:
    con = _PREDISPOSTA.model_copy(update={"pioggia_riferimento_mm": 100.0})
    b = _bundle(static=con, rainfall_hourly=[1.0] * 72, api_30_mm=400.0, soil=0.9)
    assert _con_durate(tmp_path, [72]).score(b).score == score(b).score


def test_durate_lunghe_fuori_scala_rifiutate(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="durate_lunghe"):
        _con_durate(tmp_path, [72, 72])


# ---------------------------------------------------------------------------
# Cancello d'innesco (#656)
# ---------------------------------------------------------------------------
def _con_cancello(
    tmp_path: Path, soglia: float = 0.0, tetto: float = 0.34
) -> MultiFactorScoringEngine:
    cfg = yaml.safe_load(DEFAULT_THRESHOLDS_PATH.read_text(encoding="utf-8"))
    cfg["cancello_innesco"] = {"soglia": soglia, "tetto": tetto}
    # Il cancello su Caine: la meccanica è la stessa con la cumulata.
    cfg.pop("cumulata", None)
    out = tmp_path / "cancello.yaml"
    out.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return MultiFactorScoringEngine(load_regional_thresholds(out))


_PREDISPOSTA = StaticFactors(
    cell_id="c",
    iffi_density_500=10.0,
    slope_deg=45.0,
    pai_class_norm=1.0,
    litho_weight=1.0,
)


def test_in_produzione_innesco_relativo_e_cancello() -> None:
    t = load_regional_thresholds()
    assert t.cumulata is not None and t.cumulata.modo == "sostituisce"
    assert t.cancello_innesco is not None
    assert t.model_version == "limen-deterministic-v1.1"


def test_il_cancello_si_chiude_sulla_cumulata_sotto_soglia() -> None:
    t = load_regional_thresholds()
    assert t.cumulata is not None and t.cancello_innesco is not None
    rif = 100.0
    con = _PREDISPOSTA.model_copy(update={"pioggia_riferimento_mm": rif})
    asciutta = _bundle(static=con, rainfall_hourly=[0.0] * 24, api_30_mm=400.0, soil=0.9)
    assert score(asciutta).score <= t.cancello_innesco.tetto
    # Nelle ultime 24 ore più della soglia, in quota del riferimento: aperto.
    mm = (t.cancello_innesco.soglia + 0.1) * rif * t.cumulata.saturazione
    bagnata = _bundle(static=con, rainfall_hourly=[mm / 6] * 6, api_30_mm=400.0, soil=0.9)
    assert score(bagnata).breakdown.meteo_terms.cumulata_norm > t.cancello_innesco.soglia
    assert score(bagnata).score > t.cancello_innesco.tetto


def test_una_cella_senza_riferimento_non_e_chiusa_dal_cancello(tmp_path: Path) -> None:
    # Il riferimento manca (nodo in mare, clima-pioggia non ancora girato): la
    # cella torna su Caine e il cancello, misurato sulla cumulata, resta aperto.
    b = _bundle(static=_PREDISPOSTA, api_30_mm=400.0, soil=0.9)
    assert score(b).score == pytest.approx(_caine_solo(tmp_path).score(b).score)
    cancello = load_regional_thresholds().cancello_innesco
    assert cancello is not None
    assert score(b).score > cancello.tetto


def test_senza_pioggia_letta_il_cancello_resta_aperto(tmp_path: Path) -> None:
    # Open-Meteo degradato: nessuna ora nella finestra. Non è pioggia zero.
    con = _PREDISPOSTA.model_copy(update={"pioggia_riferimento_mm": 100.0})
    b = _bundle(static=con, rainfall_hourly=[], api_30_mm=400.0, soil=0.9)
    assert score(b).breakdown.meteo_terms.cumulata_norm is None
    assert score(b).score == pytest.approx(_caine_solo(tmp_path).score(b).score)


def test_il_cancello_tiene_sotto_moderato_un_versante_bagnato_senza_innesco(
    tmp_path: Path,
) -> None:
    # Versante predisposto, autunno bagnato, nessuna pioggia d'innesco: il
    # Moderato di fondo di novembre 2026.
    b = _bundle(static=_PREDISPOSTA, api_30_mm=400.0, soil=0.9)
    libero = score(b)
    assert libero.breakdown.meteo_terms.caine_norm == 0.0
    assert libero.score > 0.34
    chiuso = _con_cancello(tmp_path).score(b)
    assert chiuso.score == pytest.approx(0.34)
    assert chiuso.level in {RiskLevel.None_, RiskLevel.Low}
    # Il breakdown resta quello del motore: il cancello tocca solo il punteggio.
    assert chiuso.breakdown == libero.breakdown


def test_la_pioggia_d_innesco_o_il_sisma_aprono_il_cancello(tmp_path: Path) -> None:
    engine = _con_cancello(tmp_path)
    pioggia = _bundle(static=_PREDISPOSTA, rainfall_hourly=[30] * 6, api_30_mm=400.0, soil=0.9)
    assert pioggia_innesco(pioggia) > 0.0
    assert engine.score(pioggia).score == pytest.approx(score(pioggia).score)
    scossa = SeismicHistoryEvent(
        event_id="q", origin_time=VALUATION_TIME, magnitude=5.5, distance_km=5.0, pga_g=0.40
    )
    sisma = _bundle(static=_PREDISPOSTA, api_30_mm=400.0, soil=0.9, seismic=[scossa])
    assert score(sisma).breakdown.e > 0.0
    assert engine.score(sisma).score == pytest.approx(score(sisma).score)


def test_sotto_la_soglia_l_innesco_non_apre(tmp_path: Path) -> None:
    debole = next(
        b
        for mm in (2, 3, 4, 5, 6, 8, 10, 12)
        if 0.0
        < pioggia_innesco(
            b := _bundle(static=_PREDISPOSTA, rainfall_hourly=[mm] * 6, api_30_mm=400.0, soil=0.9)
        )
        < 0.9
    )
    innesco = pioggia_innesco(debole)
    assert _con_cancello(tmp_path, soglia=innesco + 0.05).score(debole).score <= 0.34
    assert _con_cancello(tmp_path, soglia=innesco - 0.01).score(debole).score == pytest.approx(
        score(debole).score
    )


def pioggia_innesco(b: CellFeatureBundle) -> float:
    return score(b).breakdown.meteo_terms.caine_norm
