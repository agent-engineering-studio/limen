"""Le portate GloFAS storiche su disco, e il backtest che le rilegge (#478)."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from limen.cli import backtest_flood
from limen.integrations.openmeteo import archivio_portate as ap

NODI = [(11.25, 44.25), (11.5, 44.25)]
DAL, AL = date(2023, 1, 1), date(2024, 12, 31)


def _risposta(nodi: list[tuple[float, float]], dal: date, al: date, *, vuoti: set[int]) -> Any:
    giorni = [dal + timedelta(days=i) for i in range((al - dal).days + 1)]
    return [
        {"daily": {}}
        if k in vuoti
        else {
            "daily": {
                "time": [g.isoformat() for g in giorni],
                "river_discharge": [7.0] * len(giorni),
            }
        }
        for k in range(len(nodi))
    ]


class _Api:
    """L'API pubblica finta: registra i nodi chiesti, e quali posizioni tornano vuote."""

    def __init__(self) -> None:
        self.chiamate: list[list[tuple[float, float]]] = []
        self.vuoti: set[int] = set()

    async def fetch_grid(
        self, _url: str, nodi: list[tuple[float, float]], params: dict[str, str], _label: str
    ) -> Any:
        self.chiamate.append(list(nodi))
        return _risposta(
            nodi,
            date.fromisoformat(params["start_date"]),
            date.fromisoformat(params["end_date"]),
            vuoti=self.vuoti,
        )


@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Api:
    from limen.integrations.openmeteo import flood

    monkeypatch.setenv("LIMEN_DATA_ROOT", str(tmp_path))
    finta = _Api()
    monkeypatch.setattr(flood, "OpenMeteoFloodClient", lambda: finta)
    return finta


def test_scrivi_e_rileggi(tmp_path: Path) -> None:
    serie = ap.SerieNodo(dal=DAL, al=AL, portate={DAL: 3.5, AL: 4.0})
    assert ap.scrivi(tmp_path, NODI[0], serie)
    letta = ap.leggi(tmp_path, NODI[0])
    assert letta == serie
    assert letta.copre(DAL + timedelta(days=10), AL)
    assert not letta.copre(DAL - timedelta(days=1), AL)


def test_una_serie_vuota_non_si_scrive(tmp_path: Path) -> None:
    assert not ap.scrivi(tmp_path, NODI[0], ap.SerieNodo(dal=DAL, al=AL, portate={}))
    assert ap.leggi(tmp_path, NODI[0]) is None


async def test_il_secondo_backtest_non_richiede_niente(
    api: _Api,
) -> None:
    prima = await backtest_flood._fetch_discharges(NODI, start=DAL, end=AL)
    seconda = await backtest_flood._fetch_discharges(NODI, start=DAL + timedelta(days=30), end=AL)
    assert api.chiamate == [NODI]
    assert prima == seconda
    assert all(len(s) == (AL - DAL).days + 1 for s in seconda.values())


async def test_un_nodo_vuoto_si_richiede_e_gli_altri_no(
    api: _Api,
) -> None:
    api.vuoti.add(1)
    await backtest_flood._fetch_discharges(NODI, start=DAL, end=AL)
    api.vuoti.clear()
    out = await backtest_flood._fetch_discharges(NODI, start=DAL, end=AL)
    # Il nodo vuoto non era stato salvato: si richiede lui solo.
    assert api.chiamate == [NODI, [NODI[1]]]
    assert all(out.values())


async def test_un_arco_piu_lungo_allarga_quello_salvato(
    api: _Api,
) -> None:
    await backtest_flood._fetch_discharges(NODI, start=DAL, end=AL)
    out = await backtest_flood._fetch_discharges(NODI, start=DAL, end=AL + timedelta(days=60))
    assert len(api.chiamate) == 2
    salvata = ap.leggi(ap.cartella(), NODI[0])
    assert salvata is not None and salvata.copre(DAL, AL + timedelta(days=60))
    assert max(out[0]) == AL + timedelta(days=60)


def test_la_testa_del_report_dice_se_il_ramo_fluviale_e_misurato() -> None:
    assert "solo ramo pluviale" in backtest_flood.ramo_fluviale(0, 135)
    assert backtest_flood.ramo_fluviale(98, 135) == (
        "Ramo fluviale: portata GloFAS su **98 nodi su 135**."
    )
