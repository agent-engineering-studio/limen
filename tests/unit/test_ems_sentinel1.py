"""``limen ems-sentinel1``: budget prima di spendere, send= dentro il retry di Limen."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from limen.cli import ems_sentinel1

_ORA = datetime(2026, 11, 4, 12, tzinfo=UTC)
_EVENTO = datetime(2024, 9, 18, tzinfo=UTC)


@dataclass
class _Plan:
    product: str
    backscatter_path: Path | None
    pu: float = 10.0
    scene_pass: object | None = True
    reason: str | None = None


@dataclass
class _Mondo:
    """Libreria e database sostituiti: registra cosa sarebbe successo."""

    tmp: Path
    speso: float = 0.0
    registrate: list[dict[str, Any]] = field(default_factory=list)
    coppie: list[tuple[str, str | None]] = field(default_factory=list)
    fallisce: set[str] = field(default_factory=set)
    prima_di: list[datetime] = field(default_factory=list)


@pytest.fixture()
def mondo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> _Mondo:
    from copernicus_ems import sentinelhub
    from copernicus_ems.errors import EmsError

    m = _Mondo(tmp=tmp_path)
    eventi = [
        SimpleNamespace(product=SimpleNamespace(observed_time=_EVENTO, aoi_extent=object(), n=i))
        for i in range(2)
    ]
    # Un prodotto senza osservazione non si pianifica.
    eventi.append(SimpleNamespace(product=SimpleNamespace(observed_time=None, aoi_extent=None)))

    class _Ems:
        def __init__(self, *, send: Any) -> None:
            assert send is ems_sentinel1._send

        async def observed_events(self, _code: str) -> list[Any]:
            return eventi

        async def aclose(self) -> None:
            return None

    class _Hub:
        def __init__(self, *, send: Any) -> None:
            assert send is ems_sentinel1._send
            self.pu_estimated = 0.0

        async def __aenter__(self) -> _Hub:
            return self

        async def __aexit__(self, *_a: object) -> None:
            return None

    async def plan_pair(_ems: Any, event: Any, *, resolution_m: float) -> _Plan:
        assert resolution_m == 40.0
        return _Plan(f"AOI0{event.product.n}", tmp_path / f"s1_{event.product.n}.tif")

    async def plan_reference(_ems: Any, plan: _Plan, *, before: datetime) -> _Plan:
        m.prima_di.append(before)
        return _Plan(plan.product, tmp_path / f"ref_{plan.product}.tif", pu=12.0)

    async def make_pair(hub: _Hub, plan: _Plan, *, reference: _Plan | None) -> tuple[Any, Path]:
        if plan.product in m.fallisce:
            raise EmsError("Process API answered 400")
        m.coppie.append((plan.product, reference.product if reference else None))
        hub.pu_estimated += plan.pu
        return SimpleNamespace(path=plan.backscatter_path), tmp_path / "labels.tif"

    async def attivazioni() -> list[Any]:
        return [SimpleNamespace(activation_code="EMSR762", event_time=_EVENTO)]

    async def somma(*_a: object) -> float:
        return m.speso

    async def registra(**kw: Any) -> int:
        m.registrate.append(kw)
        return 1

    import copernicus_ems

    monkeypatch.setattr(copernicus_ems, "RapidMapping", _Ems)
    monkeypatch.setattr(sentinelhub, "SentinelHub", _Hub)
    monkeypatch.setattr(sentinelhub, "plan_pair", plan_pair)
    monkeypatch.setattr(sentinelhub, "plan_reference", plan_reference)
    monkeypatch.setattr(sentinelhub, "make_pair", make_pair)
    monkeypatch.setattr(ems_sentinel1.flood_events_repo, "activations_summary", attivazioni)
    monkeypatch.setattr(ems_sentinel1.dataset_versions_repo, "sum_metadata_since", somma)
    monkeypatch.setattr(ems_sentinel1.dataset_versions_repo, "record", registra)
    return m


@pytest.mark.asyncio
async def test_il_piano_non_spende_e_non_registra(mondo: _Mondo) -> None:
    out = await ems_sentinel1.esegui(dry_run=True, now=_ORA)
    assert out["esito"] == "piano"
    # Due eventi e due riferimenti, nessuno su disco: 10 + 10 + 12 + 12.
    assert out["pu_da_spendere"] == 44.0
    assert mondo.coppie == [] and mondo.registrate == []


@pytest.mark.asyncio
async def test_il_riferimento_precede_l_inizio_dell_alluvione(mondo: _Mondo) -> None:
    await ems_sentinel1.esegui(dry_run=True, now=_ORA)
    assert mondo.prima_di == [datetime(2024, 9, 17, tzinfo=UTC)] * 2


@pytest.mark.asyncio
async def test_oltre_il_budget_del_mese_non_parte_niente(mondo: _Mondo) -> None:
    mondo.speso = 990.0  # tetto di default 1000: 990 + 44 lo supera
    out = await ems_sentinel1.esegui(dry_run=False, now=_ORA)
    assert out["esito"] == "oltre_budget"
    assert mondo.coppie == [] and mondo.registrate == []


@pytest.mark.asyncio
async def test_la_spesa_si_registra_prima_e_nel_mese(mondo: _Mondo) -> None:
    out = await ems_sentinel1.esegui(dry_run=False, now=_ORA)
    assert out["esito"] == "scritto"
    assert mondo.coppie == [("AOI00", "AOI00"), ("AOI01", "AOI01")]
    (riga,) = mondo.registrate
    assert riga["metadata"] == {"pu": 44.0, "immagini": 4}
    assert riga["version"].startswith("2026-11:")


@pytest.mark.asyncio
async def test_le_immagini_gia_su_disco_non_si_pagano(mondo: _Mondo) -> None:
    for nome in ("s1_0.tif", "s1_1.tif", "ref_AOI00.tif", "ref_AOI01.tif"):
        (mondo.tmp / nome).write_bytes(b"tif")
    mondo.speso = 1000.0  # tetto pieno: con zero da spendere si riscrivono le etichette
    out = await ems_sentinel1.esegui(dry_run=False, now=_ORA)
    assert out["pu_da_spendere"] == 0.0
    assert out["esito"] == "scritto"
    assert mondo.registrate == []
    assert len(mondo.coppie) == 2


@pytest.mark.asyncio
async def test_una_coppia_che_fallisce_non_ferma_le_altre(mondo: _Mondo) -> None:
    mondo.fallisce = {"AOI00"}
    out = await ems_sentinel1.esegui(dry_run=False, now=_ORA)
    assert out["fallite"] == ["AOI00"]
    assert out["scritte"] == 1


@pytest.mark.asyncio
async def test_send_passa_la_richiesta_intera_a_fetch_with_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    visto: dict[str, Any] = {}

    async def finto(method: str, url: str, **kw: Any) -> httpx.Response:
        visto.update(method=method, url=url, **kw)
        return httpx.Response(200)

    monkeypatch.setattr(ems_sentinel1, "fetch_with_retry", finto)
    req = httpx.Request(
        "POST",
        "https://sh.dataspace.copernicus.eu/api/v1/process",
        json={"a": 1},
        headers={"Authorization": "Bearer t"},
    )
    await ems_sentinel1._send(req)
    assert (visto["method"], visto["url"]) == ("POST", str(req.url))
    assert visto["headers"]["authorization"] == "Bearer t"
    assert visto["content"] == b'{"a":1}'
    assert visto["timeout"].read == 300.0
