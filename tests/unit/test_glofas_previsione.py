"""La previsione GloFAS dall'EWDS: quale corsa, e quando non si scarica niente."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr

from limen.config.settings import CopernicusSettings, Settings
from limen.integrations.copernicus import ewds_glofas, glofas_previsione

_OGGI = date(2026, 10, 11)
_NODI = [(11.9, 44.3), (12.1, 44.4)]


def _settings(chiave: str | None, tmp_path: Path) -> Settings:
    return Settings(
        copernicus=CopernicusSettings(
            ewds_key=SecretStr(chiave) if chiave is not None else None, cartella=str(tmp_path)
        )
    )


@pytest.fixture
def repo(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    stato: dict[str, Any] = {"ultima": None, "salvate": []}

    async def ultima_corsa() -> date | None:
        return stato["ultima"]  # type: ignore[no-any-return]

    async def nodi_con_fiume(**_kw: Any) -> list[tuple[float, float]]:
        return _NODI

    async def salva_previsione(corsa: date, picchi: dict[Any, float], *, fonte: str) -> int:
        stato["salvate"].append((corsa, picchi, fonte))
        return len(picchi)

    from limen.data.repos import glofas_repo

    monkeypatch.setattr(glofas_repo, "ultima_corsa", ultima_corsa)
    monkeypatch.setattr(glofas_repo, "nodi_con_fiume", nodi_con_fiume)
    monkeypatch.setattr(glofas_repo, "salva_previsione", salva_previsione)
    monkeypatch.setattr(ewds_glofas, "nuovo_client", lambda _u, _k: object())
    monkeypatch.setattr(ewds_glofas, "picchi_per_nodo", lambda _p, nodi: dict.fromkeys(nodi, 5.0))
    return stato


async def test_senza_chiave_non_si_scarica_niente(tmp_path: Path, repo: dict[str, Any]) -> None:
    esito = await glofas_previsione.aggiorna(_settings(None, tmp_path), oggi=_OGGI)
    assert esito["status"] == "skipped"
    assert repo["salvate"] == []


async def test_se_la_corsa_di_oggi_non_c_e_si_prende_quella_di_ieri(
    tmp_path: Path, repo: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    chieste: list[date] = []

    def scarica(_cartella: Path, corsa: date, *, client: Any) -> Path:
        chieste.append(corsa)
        if corsa == _OGGI:
            raise RuntimeError("not available yet")
        return tmp_path / "x.nc"

    monkeypatch.setattr(ewds_glofas, "scarica_previsione", scarica)
    esito = await glofas_previsione.aggiorna(_settings("k", tmp_path), oggi=_OGGI)

    assert chieste == [_OGGI, date(2026, 10, 10)]
    assert esito == {"status": "ok", "corsa": "2026-10-10", "salvati": 2}
    assert repo["salvate"][0][2] == "ewds:operational"


async def test_una_corsa_gia_salvata_non_si_riscarica(
    tmp_path: Path, repo: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    chieste: list[date] = []

    def scarica(_cartella: Path, corsa: date, *, client: Any) -> Path:
        chieste.append(corsa)
        raise RuntimeError("not available yet")

    monkeypatch.setattr(ewds_glofas, "scarica_previsione", scarica)
    repo["ultima"] = date(2026, 10, 10)
    esito = await glofas_previsione.aggiorna(_settings("k", tmp_path), oggi=_OGGI)

    # Si prova oggi; ieri c'è già.
    assert chieste == [_OGGI]
    assert esito["salvati"] == 0
    assert repo["salvate"] == []
