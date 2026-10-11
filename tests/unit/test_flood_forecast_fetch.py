"""Flood-signal fetch: executor wiring + client parsing/degradation (issue #8)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from limen.agents.executors.flood_forecast_fetch import FloodForecastFetchExecutor
from limen.core.models.context import MonitoringContext
from limen.integrations.openmeteo.flood import FloodSignals, OpenMeteoFloodClient

_T0 = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


class _FakeClient:
    def __init__(self, sig: FloodSignals) -> None:
        self._sig = sig

    async def fetch_signals(self, **_kw: Any) -> FloodSignals:
        return self._sig


@pytest.mark.asyncio
async def test_executor_sets_signals_on_context() -> None:
    ctx = MonitoringContext(aoi_id="it-puglia", valuation_time=_T0, bbox=(16.0, 40.0, 17.0, 41.0))
    client = _FakeClient(
        FloodSignals(rain_72h_mm=120.0, river_discharge_ratio=3.0, coastal_surge_norm=0.2)
    )
    out = await FloodForecastFetchExecutor(client=client).run(ctx)
    assert out.flood_forecast_rain_72h_mm == 120.0
    assert out.river_discharge_ratio == 3.0
    assert out.coastal_surge_norm == 0.2


@pytest.mark.asyncio
async def test_executor_without_bbox_is_a_noop() -> None:
    ctx = MonitoringContext(aoi_id="it-puglia", valuation_time=_T0)
    out = await FloodForecastFetchExecutor(client=_FakeClient(FloodSignals())).run(ctx)
    assert out.flood_forecast_rain_72h_mm is None


@pytest.mark.asyncio
async def test_client_pluvial_sums_precip(monkeypatch: pytest.MonkeyPatch) -> None:
    c = OpenMeteoFloodClient()

    async def fake_get(url: str, params: dict[str, Any], label: str) -> dict[str, Any]:
        return {"hourly": {"precipitation": [1.0, 2.0, None, 3.0]}}

    monkeypatch.setattr(c, "_get", fake_get)
    assert await c._pluvial(16.0, 41.0, _T0, 72) == 6.0


@pytest.mark.asyncio
async def test_client_fluvial_ratio_peak_over_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    c = OpenMeteoFloodClient()

    async def fake_get(url: str, params: dict[str, Any], label: str) -> dict[str, Any]:
        # 31 past days at 10 + 7 forecast with a peak of 30 → 30 / 10 = 3.0
        return {
            "daily": {"river_discharge": [10.0] * 31 + [30.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0]}
        }

    monkeypatch.setattr(c, "_get", fake_get)
    assert await c._fluvial(16.0, 41.0) == pytest.approx(3.0)


@pytest.mark.asyncio
async def test_client_coastal_none_inland(monkeypatch: pytest.MonkeyPatch) -> None:
    c = OpenMeteoFloodClient()

    async def fake_get(url: str, params: dict[str, Any], label: str) -> dict[str, Any]:
        return {"hourly": {"wave_height": []}}  # inland → no marine data

    monkeypatch.setattr(c, "_get", fake_get)
    assert await c._coastal(16.0, 41.0) is None


@pytest.mark.asyncio
async def test_client_degrades_to_none_when_get_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    c = OpenMeteoFloodClient()

    async def fake_get(url: str, params: dict[str, Any], label: str) -> None:
        return None  # simulate a degraded HTTP fetch

    monkeypatch.setattr(c, "_get", fake_get)
    sig = await c.fetch_signals(bbox=(16.0, 40.0, 17.0, 41.0), valuation_time=_T0)
    assert sig == FloodSignals(None, None, None)


# ---------------------------------------------------------------------------
# Ramo fluviale per nodo: il rapporto e il suo denominatore (#108)
# ---------------------------------------------------------------------------
_NODES = [(11.9, 44.3), (12.1, 44.4), (10.9, 44.9)]


def _grid(
    monkeypatch: pytest.MonkeyPatch, answers: dict[str, list[list[float] | None]]
) -> list[str]:
    """Sostituisce la richiesta multi-punto, instradando per etichetta."""
    seen: list[str] = []

    async def _fetch_grid(
        _self: Any, _url: str, nodes: list[Any], _params: dict[str, Any], label: str
    ) -> list[dict[str, Any]]:
        seen.append(label)
        series = answers[label]
        return [{} if s is None else {"daily": {"river_discharge": s}} for s in series]

    monkeypatch.setattr(OpenMeteoFloodClient, "fetch_grid", _fetch_grid)
    return seen


async def test_the_reference_is_the_node_own_high_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    """Due anni di storia del nodo, non un numero regionale: è questo che
    rende il rapporto confrontabile fra il Po e un suo affluente."""
    _grid(
        monkeypatch,
        {
            "openmeteo.flood.discharge_reference": [
                [float(k) for k in range(400)],  # q90 = 359,1
                [5.0] * 100,  # storia troppo corta: nessun riferimento
                None,  # lotto degradato
            ]
        },
    )
    client = OpenMeteoFloodClient()

    reference = await client.discharge_reference(_NODES, percentile=0.90, window_days=730)

    assert reference[0] == pytest.approx(359.1)
    assert reference[1] is None
    assert reference[2] is None


async def test_fluvial_ratio_divides_by_the_node_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Il fosso e il fiume arrivano allo stesso numero quando sono entrambi
    al doppio della loro piena ordinaria: prima il fosso faceva 62 e il fiume
    1,25, ed è per questo che serviva un filtro (#108)."""
    _grid(
        monkeypatch,
        {
            "openmeteo.flood.fluvial_grid": [
                [1.0, 0.6, 0.4],  # fosso: picco 1,0 su piena ordinaria 0,5
                [40.0, 900.0, 80.0],  # fiume: picco 900 su piena ordinaria 450
                [10.0],
            ]
        },
    )
    client = OpenMeteoFloodClient()

    ratios = await client._fluvial_by_node(_NODES, reference=[0.5, 450.0, None])

    assert ratios[0] == pytest.approx(2.0)
    assert ratios[1] == pytest.approx(2.0)
    # Nessun riferimento: "non so quanto è grande", non "il fiume è in secca".
    assert ratios[2] is None


async def test_a_node_the_grid_did_not_answer_for_has_no_ratio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _grid(monkeypatch, {"openmeteo.flood.fluvial_grid": [None, [30.0], None]})
    ratios = await OpenMeteoFloodClient()._fluvial_by_node(_NODES, reference=[10.0, 10.0, 10.0])
    assert ratios == [None, 3.0, None]


class _Cache:
    def __init__(self, stored: Any = None) -> None:
        self.stored = stored
        self.writes: list[tuple[str, Any, int]] = []

    async def get_json(self, _key: str) -> Any:
        return self.stored

    async def set_json(self, key: str, value: Any, *, ttl_seconds: int) -> None:
        self.writes.append((key, value, ttl_seconds))


async def test_il_riferimento_si_legge_dalla_tabella_e_non_si_ricompra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Due anni d'archivio per nodo esaurivano il tetto giornaliero in diciotto
    minuti (#200): lo sweep il riferimento lo legge e basta, e un nodo non
    ancora calcolato vale «non so»."""
    seen = _grid(monkeypatch, {"openmeteo.flood.discharge_reference": []})

    async def _tabella(
        nodes: list[tuple[float, float]], *, percentile: float, window_days: int
    ) -> dict[tuple[float, float], float | None]:
        assert (percentile, window_days) == (0.9, 730)
        return {_NODES[0]: 12.5, _NODES[2]: None}

    reference = await OpenMeteoFloodClient(riferimenti=_tabella)._cached_reference(
        _NODES, percentile=0.9, window_days=730
    )

    assert reference == [12.5, None, None]
    assert seen == []


async def test_una_tabella_irraggiungibile_non_ferma_lo_sweep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _grid(monkeypatch, {"openmeteo.flood.discharge_reference": []})

    async def _giu(
        nodes: list[tuple[float, float]], *, percentile: float, window_days: int
    ) -> dict[tuple[float, float], float | None]:
        raise ConnectionError("database giù")

    reference = await OpenMeteoFloodClient(riferimenti=_giu)._cached_reference(
        _NODES, percentile=0.9, window_days=730
    )
    assert reference == [None, None, None]
    assert seen == []


async def test_la_previsione_si_chiede_solo_per_i_nodi_con_un_fiume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chiedere la portata di nodi in mare o senza riferimento bruciava quota
    per un rapporto che sarebbe comunque «non so» (#200)."""
    chiesti: list[list[Any]] = []

    async def _fetch_grid(
        _self: Any, _url: str, nodes: list[Any], _params: dict[str, Any], label: str
    ) -> list[dict[str, Any]]:
        chiesti.append(list(nodes))
        return [{"daily": {"river_discharge": [20.0]}} for _ in nodes]

    monkeypatch.setattr(OpenMeteoFloodClient, "fetch_grid", _fetch_grid)
    ratios = await OpenMeteoFloodClient(cache=_Cache())._cached_fluvial_by_node(
        _NODES, reference=[10.0, None, 0.0]
    )
    assert chiesti == [[_NODES[0]]]
    assert ratios == [2.0, None, None]


async def test_la_previsione_fluviale_in_cache_non_si_ricompra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GloFAS gira una volta al giorno: richiederla a ogni tick orario non la
    aggiorna, la ricompra — 8538 località per ventiquattro, che è metà di ciò
    che ha esaurito il tetto giornaliero di Open-Meteo (#142)."""
    seen = _grid(monkeypatch, {"openmeteo.flood.fluvial_grid": []})
    cache = _Cache(stored=[0.5, None, 2.0])

    ratios = await OpenMeteoFloodClient(cache=cache)._cached_fluvial_by_node(
        _NODES, reference=[10.0, 10.0, 10.0]
    )

    assert ratios == [0.5, None, 2.0]
    assert seen == []
    assert cache.writes == []


async def test_la_previsione_fluviale_riempie_la_cache_con_la_scadenza_giusta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _grid(monkeypatch, {"openmeteo.flood.fluvial_grid": [[30.0], [5.0], None]})
    cache = _Cache()

    ratios = await OpenMeteoFloodClient(cache=cache)._cached_fluvial_by_node(
        _NODES, reference=[10.0, 10.0, 10.0]
    )

    (key, value, ttl) = cache.writes[0]
    assert key.startswith("flood:fluvial_forecast:")
    assert value == ratios
    assert ttl == 24 * 3600  # una corsa GloFAS al giorno


async def test_un_degrado_non_finisce_in_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un 429 svuota la griglia. Scriverlo terrebbe l'AOI a secco per sei ore
    per un singolo errore di rete, che è esattamente il guasto da evitare."""
    _grid(monkeypatch, {"openmeteo.flood.fluvial_grid": [None, None, None]})
    cache = _Cache()

    ratios = await OpenMeteoFloodClient(cache=cache)._cached_fluvial_by_node(
        _NODES, reference=[10.0, 10.0, 10.0]
    )

    assert ratios == [None, None, None]
    assert cache.writes == []


async def test_la_previsione_restante_esclude_le_ore_gia_osservate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Con 24 ore misurate dal radar, della finestra di 72 restano 48 (#199):
    sommare la prevista intera alla misurata farebbe una finestra di 96."""
    stamps = [(_T0 + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(80)]

    async def _fetch_grid(
        _self: Any, _url: str, nodes: list[Any], _params: dict[str, Any], label: str
    ) -> list[dict[str, Any]]:
        return [{"hourly": {"time": stamps, "precipitation": [1.0] * 80}} for _ in nodes]

    monkeypatch.setattr(OpenMeteoFloodClient, "fetch_grid", _fetch_grid)
    totale, resto = await OpenMeteoFloodClient()._pluvial_by_node(
        [(16.0, 40.0)], _T0, 72, head_hours=48
    )
    assert totale == [73.0]
    assert resto == [49.0]


async def test_con_una_corsa_ewds_la_previsione_non_si_chiede_a_open_meteo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La corsa salvata in `glofas_previsione` è la stessa GloFAS 4 che
    Open-Meteo serve: letta dalla tabella, il tetto giornaliero non conta."""
    seen = _grid(monkeypatch, {"openmeteo.flood.fluvial_grid": []})
    chiesti: list[Any] = []

    async def _corsa(
        nodes: list[tuple[float, float]], *, dal: Any
    ) -> dict[tuple[float, float], float] | None:
        chiesti.append((list(nodes), dal))
        return {_NODES[0]: 30.0}

    ratios = await OpenMeteoFloodClient(cache=_Cache(), previsioni=_corsa)._cached_fluvial_by_node(
        _NODES, reference=[10.0, 10.0, None]
    )

    assert ratios == [3.0, None, None]
    assert seen == []
    assert chiesti[0][0] == [_NODES[0], _NODES[1]]


async def test_senza_una_corsa_recente_si_torna_a_open_meteo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _grid(monkeypatch, {"openmeteo.flood.fluvial_grid": [[30.0], [5.0], None]})

    async def _nessuna(
        nodes: list[tuple[float, float]], *, dal: Any
    ) -> dict[tuple[float, float], float] | None:
        return None

    ratios = await OpenMeteoFloodClient(
        cache=_Cache(), previsioni=_nessuna
    )._cached_fluvial_by_node(_NODES, reference=[10.0, 10.0, 10.0])
    assert ratios == [3.0, 0.5, None]


async def test_una_tabella_previsioni_irraggiungibile_torna_a_open_meteo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _grid(monkeypatch, {"openmeteo.flood.fluvial_grid": [[30.0], [5.0], None]})

    async def _giu(
        nodes: list[tuple[float, float]], *, dal: Any
    ) -> dict[tuple[float, float], float] | None:
        raise ConnectionError("database giù")

    ratios = await OpenMeteoFloodClient(cache=_Cache(), previsioni=_giu)._cached_fluvial_by_node(
        _NODES, reference=[10.0, 10.0, 10.0]
    )
    assert ratios == [3.0, 0.5, None]
