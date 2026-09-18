"""Unit tests for the shared rainfall-node grid helpers (pure)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from limen.integrations.openmeteo.grid import build_rain_nodes, nearest_node


def test_build_rain_nodes_covers_bbox() -> None:
    bbox = (16.0, 40.0, 16.5, 40.5)
    nodes = build_rain_nodes(bbox, spacing=0.25)
    # 0.0, 0.25, 0.5 along each axis inclusive → 3 x 3.
    assert len(nodes) == 9
    assert (16.0, 40.0) in nodes
    assert any(abs(lon - 16.5) < 1e-9 and abs(lat - 40.5) < 1e-9 for lon, lat in nodes)


def test_build_rain_nodes_degenerate_bbox_falls_back_to_centroid() -> None:
    # A zero-area bbox still yields exactly one node (its centre).
    nodes = build_rain_nodes((16.0, 40.0, 16.0, 40.0), spacing=0.25)
    assert nodes == [(16.0, 40.0)]


def test_nearest_node_picks_closest() -> None:
    nodes = [(16.0, 40.0), (16.5, 40.0), (16.0, 40.5)]
    assert nearest_node(16.05, 40.02, nodes) == 0
    assert nearest_node(16.48, 40.03, nodes) == 1
    assert nearest_node(16.02, 40.47, nodes) == 2


def test_a_window_without_timezone_is_read_as_utc(monkeypatch: pytest.MonkeyPatch) -> None:
    """`LIMEN_BACKTEST_START=2019-11-01` non porta il fuso, e piu' avanti finiva
    a confronto con i campioni di pioggia, che ce l'hanno: il comando moriva a
    meta' con "can't compare offset-naive and offset-aware datetimes". Il
    default e' gia' in UTC, quindi il difetto si vedeva solo passando la
    finestra da variabile d'ambiente — cioe' sempre, quando si sceglie
    l'evento da rigiocare."""
    from limen.cli.backtest import _parse_dt

    default = datetime(2018, 10, 1, tzinfo=UTC)
    monkeypatch.setenv("LIMEN_TEST_WINDOW", "2019-11-01")
    assert _parse_dt("LIMEN_TEST_WINDOW", default) == datetime(2019, 11, 1, tzinfo=UTC)

    monkeypatch.setenv("LIMEN_TEST_WINDOW", "2019-11-01T06:00:00+02:00")
    parsed = _parse_dt("LIMEN_TEST_WINDOW", default)
    assert parsed.utcoffset() == timedelta(hours=2)

    monkeypatch.delenv("LIMEN_TEST_WINDOW")
    assert _parse_dt("LIMEN_TEST_WINDOW", default) is default


# ---------------------------------------------------------------------------
# Confronto fra allerte ed eventi
# ---------------------------------------------------------------------------
_EVENTO = datetime(2019, 11, 24, 6, tzinfo=UTC)


def _ore(*offset: float) -> list[datetime]:
    """Istanti di allerta, espressi in ore PRIMA dell'evento."""
    return [_EVENTO - timedelta(hours=h) for h in offset]


def test_una_cella_in_allerta_prima_dell_evento_e_un_hit() -> None:
    from limen.cli.backtest import _match_truth

    hits, misses, leads = _match_truth({"c1": _ore(30.0)}, {"c1": _EVENTO}, lead_max_hours=120.0)
    assert (hits, misses) == (1, 0)
    assert leads == [30.0]


def test_la_prima_allerta_fuori_orizzonte_non_cancella_quelle_dentro() -> None:
    """Il difetto che rendeva illeggibile il backtest frane: si guardava solo
    l'allerta piu' antica, quindi una cella accesa dal primo giorno della
    finestra risultava *mancata* anche se al momento della frana era in
    allerta da giorni. Misurato in Liguria a `Moderate`: 72% delle ore-cella
    in allerta e 118 mancate su 131."""
    from limen.cli.backtest import _match_truth

    # 550 h prima (fuori orizzonte) e 40 h prima (dentro).
    hits, misses, leads = _match_truth(
        {"c1": _ore(550.0, 40.0)}, {"c1": _EVENTO}, lead_max_hours=120.0
    )
    assert (hits, misses) == (1, 0)
    # Il preavviso e' quello dell'allerta piu' precoce ancora utile.
    assert leads == [40.0]


def test_una_allerta_dopo_l_evento_non_vale() -> None:
    """Allertare a frana avvenuta non e' un preavviso."""
    from limen.cli.backtest import _match_truth

    dopo = {"c1": [_EVENTO + timedelta(hours=3)]}
    assert _match_truth(dopo, {"c1": _EVENTO}, lead_max_hours=120.0) == (0, 1, [])


def test_una_cella_mai_in_allerta_e_una_mancata() -> None:
    from limen.cli.backtest import _match_truth

    assert _match_truth({"c1": []}, {"c1": _EVENTO}, lead_max_hours=120.0) == (0, 1, [])
    assert _match_truth({}, {"c1": _EVENTO}, lead_max_hours=120.0) == (0, 1, [])
