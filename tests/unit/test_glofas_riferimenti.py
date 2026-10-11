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
        assert kw["limite"] == 3  # 160 chiamate a 730/14 ≈ 52 per nodo
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

    attese: list[float] = []

    async def _attendi(s: float) -> None:
        attese.append(s)

    esito = await gr.riempi(chiamate=160, client=_Client(), attendi=_attendi)  # type: ignore[arg-type]  # finto con la sola fetch_grid, #200

    assert [n for n, _ in salvati] == [nodi[0], nodi[2]]
    assert salvati[1][1] is None
    assert esito == {"richiesti": 3, "salvati": 2, "con_fiume": 1}
    assert attese == []  # tre nodi stanno in un lotto solo


def test_il_peso_e_una_chiamata_ogni_due_settimane() -> None:
    assert gr.peso_per_nodo(730) == pytest.approx(52.14, abs=0.01)
    assert gr.peso_per_nodo(7) == 1.0


async def test_lotti_sotto_il_limite_al_minuto(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cento nodi in un lotto pesavano ~5.200 chiamate, sopra anche il limite
    orario: è il 429 delle 00:18 dell'11 ottobre (#200)."""
    nodi = [(10.0 + k / 10, 44.0) for k in range(20)]
    lotti: list[int] = []
    attese: list[float] = []

    async def _da_calcolare(**kw: Any) -> list[tuple[float, float]]:
        return nodi[: kw["limite"]]

    async def _salva(righe: list[Any], **kw: Any) -> int:
        return len(righe)

    async def _mai_in_pausa() -> bool:
        return False

    async def _attendi(s: float) -> None:
        attese.append(s)

    class _Client:
        async def fetch_grid(self, _u: str, lotto: list[Any], _p: Any, _l: str) -> list[Any]:
            lotti.append(len(lotto))
            return [{"daily": {"river_discharge": _ANNI}} for _ in lotto]

    monkeypatch.setattr(gr.glofas_repo, "da_calcolare", _da_calcolare)
    monkeypatch.setattr(gr.glofas_repo, "salva", _salva)
    monkeypatch.setattr(gr, "_in_pausa", _mai_in_pausa)

    await gr.riempi(chiamate=1000, client=_Client(), attendi=_attendi)  # type: ignore[arg-type]  # finto, #200

    assert sum(lotti) == 19
    assert all(n * gr.peso_per_nodo(730) <= 600 for n in lotti)
    assert attese == [60.0] * (len(lotti) - 1)


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

    esito = await gr.riempi(chiamate=3000, client=_Client())  # type: ignore[arg-type]  # finto, #200
    assert esito["salvati"] == 0
