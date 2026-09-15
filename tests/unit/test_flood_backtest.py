"""Backtest alluvione: ricomposizione delle previsioni e metriche (#64).

Le due cose che il backtest può sbagliare in silenzio si provano qui, perché
sono aritmetica pura:

1. **La previsione come fu emessa.** ``precipitation_previous_dayN`` dà, per
   un'ora, la corsa di N giorni prima; ricomporre l'accumulo a 72 h dal giorno
   d vuol dire prendere d dalla corsa di d, d+1 da `previous_day1` letto su
   d+1 e d+2 da `previous_day2` letto su d+2. Sbagliare l'indice qui produce un
   backtest che sembra funzionare e misura un consuntivo.
2. **Falso contro non verificabile.** Un giorno di allerta su una cella che
   nessun passaggio satellitare ha coperto non è un falso allarme: è senza
   risposta. Contarlo fra i falsi dava FAR 100% su ogni AOI.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from limen.cli.backtest_flood import (
    FloodBacktestMetrics,
    _accumulate_72h,
    _accumulate_observed,
    _daily_sums,
    _discharge_ratios,
    _metrics,
    _midnight_values,
    _modes,
    _node_key,
    _nodes_from_cells,
    _NodeSeries,
    _parse_dt,
    _parse_level,
    _replay,
    _Tally,
    _trickle_floor,
    _unmeasurable,
    _write_report,
)
from limen.core.models.hazard import HazardType
from limen.core.models.risk import RiskLevel, StaticFactors
from limen.core.scoring.flood.engine import FloodScoringEngine
from limen.core.scoring.regional_thresholds import FloodThresholds, load_hazard_thresholds

D0 = date(2024, 9, 17)


def _thresholds() -> FloodThresholds:
    thresholds = load_hazard_thresholds(HazardType.FLOOD)
    assert isinstance(thresholds, FloodThresholds)
    return thresholds


# ---------------------------------------------------------------------------
# Ricomposizione della previsione emessa
# ---------------------------------------------------------------------------
def test_accumulate_72h_takes_each_day_from_the_run_issued_on_the_first() -> None:
    day0 = {D0: 10.0, D0 + timedelta(days=1): 999.0, D0 + timedelta(days=2): 999.0}
    day1 = {D0 + timedelta(days=1): 20.0}
    day2 = {D0 + timedelta(days=2): 30.0}

    out = _accumulate_72h(day0, day1, day2)

    # 10 + 20 + 30: i 999 sono l'analisi dei giorni successivi, che una
    # previsione emessa il 17 non poteva conoscere.
    assert out[D0] == 60.0


def test_accumulate_72h_skips_days_without_a_complete_run() -> None:
    day0 = {D0: 10.0}
    out = _accumulate_72h(day0, {}, {})
    # Un accumulo parziale sarebbe un accumulo più basso, cioè un allarme
    # mancato attribuito al modello invece che al dato assente.
    assert D0 not in out


def test_accumulate_observed_sums_three_consecutive_days() -> None:
    daily = {D0: 5.0, D0 + timedelta(days=1): 6.0, D0 + timedelta(days=2): 7.0}
    assert _accumulate_observed(daily)[D0] == 18.0


def test_issued_and_observed_differ_when_the_forecast_was_wrong() -> None:
    """Il caso misurato a Faenza: 209 mm caduti, 101 previsti tre giorni prima."""
    day0 = {D0: 100.0, D0 + timedelta(days=1): 60.0, D0 + timedelta(days=2): 49.0}
    day1 = {D0 + timedelta(days=1): 30.0}
    day2 = {D0 + timedelta(days=2): 20.0}

    issued = _accumulate_72h(day0, day1, day2)[D0]
    observed = _accumulate_observed(day0)[D0]

    assert issued == 150.0
    assert observed == 209.0
    assert issued < observed


# ---------------------------------------------------------------------------
# Rapporto di portata
# ---------------------------------------------------------------------------
def test_discharge_ratio_is_peak_ahead_over_recent_baseline() -> None:
    daily = {D0 - timedelta(days=k): 10.0 for k in range(1, 32)}
    daily[D0] = 10.0
    daily[D0 + timedelta(days=3)] = 40.0
    for k in (1, 2, 4, 5, 6):
        daily.setdefault(D0 + timedelta(days=k), 10.0)

    assert _discharge_ratios(daily)[D0] == 4.0


def test_discharge_ratio_absent_without_enough_baseline() -> None:
    daily = {D0: 10.0, D0 + timedelta(days=1): 40.0}
    assert D0 not in _discharge_ratios(daily)


# ---------------------------------------------------------------------------
# Nodi dalle celle
# ---------------------------------------------------------------------------
def test_node_key_snaps_to_the_nearest_global_lattice_point() -> None:
    assert _node_key(11.94, 44.28, spacing=0.1) == (119, 443)
    # Stessa identità per celle dentro la stessa maglia: è ciò che rende il
    # nodo una chiave riutilizzabile fra AOI.
    assert _node_key(11.94, 44.28, spacing=0.1) == _node_key(11.92, 44.26, spacing=0.1)
    # E identità diversa oltre il punto medio: 11,96 appartiene a 12,0.
    assert _node_key(11.96, 44.28, spacing=0.1) == (120, 443)


def test_nodes_come_from_cells_not_from_the_bounding_box() -> None:
    cells = [
        (StaticFactors(cell_id="a"), 11.94, 44.28),
        (StaticFactors(cell_id="b"), 11.92, 44.26),
        (StaticFactors(cell_id="c"), 7.10, 45.10),
    ]
    nodes, per_cell = _nodes_from_cells(cells, spacing=0.1)

    # Due nodi, non il rettangolo 7-12 E che ne conterrebbe centinaia sul mare
    # e in altre regioni.
    assert len(nodes) == 2
    assert per_cell[0] == per_cell[1] != per_cell[2]


# ---------------------------------------------------------------------------
# Metriche
# ---------------------------------------------------------------------------
def _tally(
    *,
    alert_days: dict[str, list[date]],
    truth: dict[str, datetime],
    truth_cell_days: int = 0,
    truth_alert_days: int = 0,
) -> _Tally:
    return _Tally(
        alert_days=alert_days,
        truth=truth,
        truth_cell_days=truth_cell_days,
        truth_alert_days=truth_alert_days,
        days=10,
        measurable=True,
    )


def _run(tally: _Tally, observed: dict[str, list[datetime]]) -> FloodBacktestMetrics:
    return _metrics(
        aoi_id="it-test",
        mode="issued",
        tally=tally,
        observed=observed,
        cells_scored=1,
        window_start=D0,
        thresholds=_thresholds(),
    )


def test_alert_before_the_flood_inside_the_horizon_is_a_hit() -> None:
    flood = datetime(2024, 9, 19, 6, tzinfo=UTC)
    out = _run(
        _tally(alert_days={"c1": [date(2024, 9, 18)]}, truth={"c1": flood}),
        {"c1": [flood]},
    )
    assert out.hits == 1
    assert out.misses == 0
    assert out.mean_lead_hours == 30.0


def test_alert_after_the_flood_is_not_a_hit() -> None:
    flood = datetime(2024, 9, 17, 6, tzinfo=UTC)
    out = _run(
        _tally(alert_days={"c1": [date(2024, 9, 18)]}, truth={"c1": flood}),
        {"c1": [flood]},
    )
    assert out.hits == 0
    assert out.misses == 1


def test_unobserved_alert_day_is_unverifiable_not_false() -> None:
    """Il difetto che dava FAR 100%: nessuno aveva guardato."""
    out = _run(_tally(alert_days={"c1": [D0]}, truth={}), observed={})

    assert out.false_days == 0
    assert out.unverifiable_days == 1
    # Nessun denominatore ⇒ nessun FAR inventato.
    assert out.far == 0.0


def test_observed_dry_alert_day_is_a_false_alarm() -> None:
    passed_over = datetime(2024, 9, 18, 12, tzinfo=UTC)
    out = _run(_tally(alert_days={"c1": [D0]}, truth={}), {"c1": [passed_over]})

    assert out.false_days == 1
    assert out.unverifiable_days == 0
    assert out.far == 1.0


def test_far_counts_only_the_verifiable_days() -> None:
    passed_over = datetime(2024, 9, 18, 12, tzinfo=UTC)
    flood = datetime(2024, 9, 18, 6, tzinfo=UTC)
    tally = _tally(
        alert_days={
            "flooded": [date(2024, 9, 17)],
            "dry": [date(2024, 9, 17)],
            "unseen": [date(2024, 9, 17), date(2024, 9, 25)],
        },
        truth={"flooded": flood},
    )
    out = _run(tally, {"flooded": [passed_over], "dry": [passed_over]})

    assert (out.true_days, out.false_days, out.unverifiable_days) == (1, 1, 2)
    assert out.far == 0.5


def test_persistent_alert_is_measured_per_day_but_counted_as_one_warning() -> None:
    """Il bordo che l'episodio sbagliava: 18 giorni accesi, evento in fondo."""
    flood = datetime(2024, 9, 20, 6, tzinfo=UTC)
    days = [date(2024, 9, 3) + timedelta(days=k) for k in range(18)]
    out = _run(_tally(alert_days={"c1": days}, truth={"c1": flood}), {"c1": [flood]})

    assert out.hits == 1, "l'allerta era accesa nelle 72 h prima dell'acqua"
    assert out.alert_episodes == 1, "un avviso continuo, non diciotto"
    assert out.true_days + out.false_days + out.unverifiable_days == 18


def test_base_rate_is_the_share_of_days_a_flooded_cell_was_already_in_alert() -> None:
    out = _run(
        _tally(
            alert_days={"c1": [D0]},
            truth={"c1": datetime(2024, 9, 18, tzinfo=UTC)},
            truth_cell_days=10,
            truth_alert_days=4,
        ),
        {"c1": [datetime(2024, 9, 18, tzinfo=UTC)]},
    )
    assert out.base_rate == 0.4
    # È il metro dell'hit rate: senza, il 100% qui sopra sembrerebbe bravura.
    assert out.hit_rate == 1.0


# ---------------------------------------------------------------------------
# Replay: il ciclo che mette insieme motore, soglie e serie (#116)
# ---------------------------------------------------------------------------


def _series(*, rain: float, day: date = D0, ratio: float | None = None) -> _NodeSeries:
    return _NodeSeries(
        rain_issued={day: rain},
        rain_observed={day: rain},
        soil={day: 0.3},
        discharge_ratio={day: ratio} if ratio is not None else {},
    )


def _day_window(day: date = D0) -> tuple[datetime, datetime]:
    moment = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
    return moment, moment


def test_replay_alerts_a_mapped_cell_under_heavy_rain() -> None:
    """Pioggia ben oltre la saturazione su una cella mappata come pericolosa:
    l'allerta deve accendersi, ed essere attribuita al ramo pluviale."""
    thresholds = _thresholds()
    cell = StaticFactors(cell_id="c1", flood_hazard_norm=1.0)
    start, end = _day_window()

    tally = _replay(
        aoi_id="it-test",
        mode="issued",
        cells=[(cell, 16.0, 41.0)],
        cell_node=[0],
        series=[_series(rain=thresholds.pluvial.saturation_mm * 2)],
        truth={"c1": start + timedelta(hours=12)},
        start=start,
        end=end,
        alert_level=RiskLevel.Moderate,
        thresholds=thresholds,
        engine=FloodScoringEngine(thresholds),
    )

    assert tally.days == 1
    assert tally.measurable is True
    assert tally.alert_days == {"c1": [D0]}
    assert tally.pluvial_driven == 1
    assert tally.fluvial_driven == 0
    # La cella di verità in allerta alimenta il tasso di base.
    assert tally.truth_cell_days == 1
    assert tally.truth_alert_days == 1


def test_replay_skips_cells_whose_node_is_below_both_thresholds() -> None:
    """Il pre-filtro per nodo: sotto soglia pluviale e senza portata, ogni
    cella del nodo vale zero, e valutarla sarebbe lavoro per un esito noto."""
    thresholds = _thresholds()
    cell = StaticFactors(cell_id="c1", flood_hazard_norm=1.0)
    start, end = _day_window()

    tally = _replay(
        aoi_id="it-test",
        mode="observed",
        cells=[(cell, 16.0, 41.0)],
        cell_node=[0],
        series=[_series(rain=thresholds.pluvial.threshold_mm / 2)],
        truth={},
        start=start,
        end=end,
        alert_level=RiskLevel.Low,
        thresholds=thresholds,
        engine=FloodScoringEngine(thresholds),
    )

    assert tally.alert_days == {}
    # Misurabile comunque: c'era un dato di pioggia, solo sotto soglia.
    assert tally.measurable is True


def test_replay_without_any_rain_is_not_measurable() -> None:
    """Nessun dato per il giorno: non e' "nessuna allerta", e' "non misurato".
    La differenza e' quella fra un modello muto e un modello senza ingressi."""
    thresholds = _thresholds()
    cell = StaticFactors(cell_id="c1", flood_hazard_norm=1.0)
    start, end = _day_window()
    empty = _NodeSeries(rain_issued={}, rain_observed={}, soil={}, discharge_ratio={})

    tally = _replay(
        aoi_id="it-test",
        mode="issued",
        cells=[(cell, 16.0, 41.0)],
        cell_node=[0],
        series=[empty],
        truth={},
        start=start,
        end=end,
        alert_level=RiskLevel.Low,
        thresholds=thresholds,
        engine=FloodScoringEngine(thresholds),
    )
    assert tally.measurable is False


def test_tally_merge_sums_across_windows() -> None:
    a = _Tally(
        alert_days={"c1": [D0]},
        truth={"c1": datetime(2024, 9, 18, tzinfo=UTC)},
        truth_cell_days=2,
        truth_alert_days=1,
        days=3,
        measurable=False,
        pluvial_driven=1,
    )
    b = _Tally(
        alert_days={"c1": [D0 + timedelta(days=1)], "c2": [D0]},
        truth={"c2": datetime(2024, 9, 19, tzinfo=UTC)},
        truth_cell_days=1,
        truth_alert_days=0,
        days=4,
        measurable=True,
        fluvial_driven=2,
    )
    a.merge(b)
    assert a.alert_days == {"c1": [D0, D0 + timedelta(days=1)], "c2": [D0]}
    assert set(a.truth) == {"c1", "c2"}
    assert (a.truth_cell_days, a.truth_alert_days, a.days) == (3, 1, 7)
    # Basta una finestra misurabile perche' la replica lo sia.
    assert a.measurable is True
    assert (a.pluvial_driven, a.fluvial_driven) == (1, 2)


# ---------------------------------------------------------------------------
# Riduzioni per giorno e soglia del fosso
# ---------------------------------------------------------------------------
def test_daily_sums_add_hours_and_skip_missing_values() -> None:
    stamps = ["2024-09-17T00:00", "2024-09-17T01:00", "2024-09-18T00:00"]
    assert _daily_sums(stamps, [1.0, None, 2.5]) == {D0: 1.0, D0 + timedelta(days=1): 2.5}


def test_midnight_values_keep_only_the_first_hour() -> None:
    stamps = ["2024-09-17T00:00", "2024-09-17T13:00", "2024-09-18T00:00"]
    assert _midnight_values(stamps, [0.2, 0.9, None]) == {D0: 0.2}


def test_trickle_floor_is_a_fraction_of_the_largest_baseline() -> None:
    """Il rapporto di portata e' patologico sui rigagnoli: un nodo conta come
    fiume solo sopra il 10 % del deflusso di base piu' grande dell'AOI."""
    big = {D0: 100.0, D0 + timedelta(days=1): 100.0}
    ditch = {D0: 1.0}
    assert _trickle_floor([big, ditch, {}]) == 10.0
    assert _trickle_floor([]) == 0.0


def test_unmeasurable_is_flagged_as_such() -> None:
    m = _unmeasurable("it-test", "issued", days=5)
    assert m.measurable is False
    assert m.days == 5
    assert m.hit_rate == 0.0


# ---------------------------------------------------------------------------
# Parametri da ambiente
# ---------------------------------------------------------------------------
def test_parse_dt_adds_utc_to_naive_values(monkeypatch) -> None:
    monkeypatch.setenv("LIMEN_T_DT", "2024-09-17T06:00")
    assert _parse_dt("LIMEN_T_DT") == datetime(2024, 9, 17, 6, tzinfo=UTC)
    monkeypatch.delenv("LIMEN_T_DT")
    assert _parse_dt("LIMEN_T_DT") is None


def test_parse_level_falls_back_to_high_on_a_bad_value(monkeypatch) -> None:
    from limen.cli import backtest_flood as mod

    monkeypatch.delenv(mod._LEVEL_ENV, raising=False)
    assert _parse_level() is RiskLevel.High
    monkeypatch.setenv(mod._LEVEL_ENV, "Moderate")
    assert _parse_level() is RiskLevel.Moderate
    monkeypatch.setenv(mod._LEVEL_ENV, "catastrofico")
    assert _parse_level() is RiskLevel.High


def test_modes_default_to_both(monkeypatch) -> None:
    from limen.cli import backtest_flood as mod

    monkeypatch.delenv(mod._MODE_ENV, raising=False)
    assert _modes() == ["issued", "observed"]
    monkeypatch.setenv(mod._MODE_ENV, "issued")
    assert _modes() == ["issued"]
    monkeypatch.setenv(mod._MODE_ENV, " OBSERVED ")
    assert _modes() == ["observed"]


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def _metrics_row(**over: object) -> FloodBacktestMetrics:
    base: dict[str, object] = {
        "aoi_id": "it-test",
        "mode": "issued",
        "truth_cells": 4,
        "days": 30,
        "cells_scored": 100,
        "hits": 3,
        "misses": 1,
        "alert_episodes": 2,
        "true_days": 5,
        "false_days": 5,
        "unverifiable_days": 7,
        "hit_rate": 0.75,
        "far": 0.5,
        "mean_lead_hours": 20.0,
        "base_rate": 0.25,
        "pluvial_driven": 6,
        "fluvial_driven": 1,
        "measurable": True,
        "window_start": D0,
    }
    base.update(over)
    return FloodBacktestMetrics(**base)


def test_write_report_carries_the_numbers_and_the_gate(tmp_path, monkeypatch) -> None:
    from limen.cli import backtest_flood as mod
    from limen.data.repos.flood_events_repo import ActivationSummary

    monkeypatch.setattr(mod, "REPORTS_DIR", tmp_path)
    start = datetime(2024, 9, 1, tzinfo=UTC)
    end = datetime(2024, 9, 30, tzinfo=UTC)
    provenance = {
        "source": "Copernicus EMS",
        "licence": "CC-BY",
        "credentials": "nessuna",
        "geometry": "poligoni",
        "coverage_note": "dal 2023",
        "known_limit": "copre solo le attivazioni",
    }
    activation = ActivationSummary(
        activation_code="EMSR800",
        event_time=datetime(2024, 9, 18, tzinfo=UTC),
        polygons=12,
        area_km2=3.4,
        name="Piemonte",
    )

    path = _write_report(
        aoi_id="it-test",
        start=start,
        end=end,
        runs=[
            _metrics_row(),
            # finestra issued ridotta: il report deve dirlo
            _metrics_row(mode="observed", window_start=date(2024, 9, 5)),
            _metrics_row(mode="issued", measurable=False),
            # nessun giorno verificabile: il FAR non e' un "0 %", e' assente
            _metrics_row(mode="observed", true_days=0, false_days=0, base_rate=0.0),
        ],
        provenance=provenance,
        activations=[activation],
        thresholds=_thresholds(),
    )

    text = path.read_text(encoding="utf-8")
    assert path.name == "backtest_flood_it-test_2024-09-01_2024-09-30.md"
    assert "`EMSR800`" in text and "3.4" in text
    assert "75%" in text and "3.00x" in text
    assert "non misurabile" in text
    assert "niente di verificabile" in text
    assert "(dal 2024-09-05)" in text
    if _thresholds().calibration is not None:
        assert "### Gate §2.5" in text
        assert "non valutabile" in text
