"""Il passo che riempie la portata ordinaria per nodo GloFAS (#200)."""

from __future__ import annotations

from typing import Any

import pytest

from limen.integrations.openmeteo import glofas_riferimenti as gr

_ANNI = [float(k) for k in range(400)]


def test_un_punto_di_un_lotto_fallito_non_e_una_risposta() -> None:
    """Un 429 non deve diventare «qui non c'è un fiume»."""
    assert gr.riferimento_del_punto({}, percentile=0.9) == (False, None)
    assert gr.riferimento_del_punto({"daily": {"river_discharge": [1.0] * 10}}, percentile=0.9) == (
        True,
        None,
    )
    risposto, portata = gr.riferimento_del_punto(
        {"daily": {"river_discharge": _ANNI}}, percentile=0.9
    )
    assert risposto and portata == pytest.approx(359.1)


async def test_salva_solo_cio_che_glofas_ha_risposto(monkeypatch: pytest.MonkeyPatch) -> None:
    nodi = [(11.9, 44.3), (12.1, 44.4), (10.9, 44.9)]
    salvati: list[Any] = []

    async def _da_calcolare(**kw: Any) -> list[tuple[float, float]]:
        assert kw["limite"] == 3
        return nodi

    async def _salva(righe: list[Any], **kw: Any) -> int:
        salvati.extend(righe)
        return len(righe)

    async def _mai_in_pausa() -> bool:
        return False

    class _Client:
        async def fetch_grid(self, _url: str, lotto: list[Any], _p: Any, _l: str) -> list[Any]:
            return [{"daily": {"river_discharge": _ANNI}}, {}, {"daily": {"river_discharge": []}}]

    monkeypatch.setattr(gr.glofas_repo, "da_calcolare", _da_calcolare)
    monkeypatch.setattr(gr.glofas_repo, "salva", _salva)
    monkeypatch.setattr(gr, "_in_pausa", _mai_in_pausa)

    esito = await gr.riempi(limite=3, client=_Client())  # type: ignore[arg-type]  # finto con la sola fetch_grid, #200

    assert [n for n, _ in salvati] == [nodi[0], nodi[2]]
    assert salvati[1][1] is None
    assert esito == {"richiesti": 3, "salvati": 2, "con_fiume": 1}


async def test_in_pausa_non_chiede_niente(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _da_calcolare(**_kw: Any) -> list[tuple[float, float]]:
        return [(11.9, 44.3)]

    async def _in_pausa() -> bool:
        return True

    class _Client:
        async def fetch_grid(self, *_a: Any) -> list[Any]:
            raise AssertionError("in pausa non si chiede niente a GloFAS")

    monkeypatch.setattr(gr.glofas_repo, "da_calcolare", _da_calcolare)
    monkeypatch.setattr(gr, "_in_pausa", _in_pausa)

    esito = await gr.riempi(limite=10, client=_Client())  # type: ignore[arg-type]  # finto, #200
    assert esito["salvati"] == 0
