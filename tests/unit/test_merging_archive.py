"""L'archivio locale del «Merging» DPC: cosa si salva, e come se ne ricava l'ora."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from limen.integrations.dpc import merging_archive
from limen.integrations.dpc.client import ASSENTE
from limen.integrations.dpc.merging_archive import (
    MergingArchive,
    _disaggrega,
    archivia,
    istanti,
    percorso,
)

_T = datetime(2026, 10, 10, 0, tzinfo=UTC)


def test_cum3_cade_sui_blocchi_e_srt1_su_ogni_ora() -> None:
    dal, al = datetime(2026, 10, 10, 1, 30, tzinfo=UTC), datetime(2026, 10, 10, 9, tzinfo=UTC)
    assert [t.hour for t in istanti("CUM3", dal, al)] == [3, 6, 9]
    assert [t.hour for t in istanti("SRT1", dal, al)] == list(range(2, 10))


def test_il_percorso_e_per_prodotto_e_giorno(tmp_path: Path) -> None:
    p = percorso(tmp_path, "CUM3", datetime(2026, 6, 1, 3, tzinfo=UTC))
    assert p == tmp_path / "CUM3/2026/06/01/CUM3_202606010300.tif"


@pytest.mark.parametrize(
    ("merging", "radar", "j", "atteso"),
    [
        (30.0, [1.0, 2.0, 3.0], 2, 15.0),  # il radar dice quando, il merging quanto
        (30.0, [0.0, 0.0, 0.0], 0, 10.0),  # radar cieco: tre parti uguali
        (30.0, [1.0, None, 3.0], 0, 10.0),  # un'ora di radar mancante: idem
        (None, [1.0, 2.0, 3.0], 1, 2.0),  # senza merging resta il radar
        (None, [1.0, None, 3.0], 1, None),  # senza nessuno dei due: non misurata
    ],
)
def test_la_quota_di_un_ora_nel_blocco(
    merging: float | None, radar: list[float | None], j: int, atteso: float | None
) -> None:
    assert _disaggrega(merging, radar, j) == atteso


async def test_archivia_e_idempotente_e_ritenta_i_falliti(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chiesti: list[tuple[str, datetime]] = []

    async def _scarica(prodotto: str, t: datetime) -> bytes | str | None:
        chiesti.append((prodotto, t))
        if t.hour == 3:
            return ASSENTE
        if t.hour == 4:
            return None
        return b"tif"

    monkeypatch.setattr(merging_archive, "scarica_fotogramma", _scarica)
    adesso = _T + timedelta(hours=8)  # ultimo istante: 06:00
    primo = await archivia(tmp_path, giorni=1, massimo=10_000, adesso=adesso)
    # Un 403 di cinque ore fa è un fotogramma non ancora pubblicato (#360).
    assert primo["persi"] == 0
    assert primo["falliti"] == 3  # CUM3 e SRT1 delle 03, SRT1 delle 04
    assert percorso(tmp_path, "CUM3", _T).read_bytes() == b"tif"

    chiesti.clear()
    secondo = await archivia(tmp_path, giorni=1, massimo=10_000, adesso=adesso)
    assert secondo["scaricati"] == 0
    assert sorted(chiesti) == [
        ("CUM3", _T + timedelta(hours=3)),
        ("SRT1", _T + timedelta(hours=3)),
        ("SRT1", _T + timedelta(hours=4)),
    ], "si ritenta solo quello che non è sul disco"


async def test_un_403_vecchio_e_perso_e_non_si_ritenta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chiesti: list[datetime] = []

    async def _scarica(prodotto: str, t: datetime) -> bytes | str:
        chiesti.append(t)
        return ASSENTE if t == _T else b"tif"

    monkeypatch.setattr(merging_archive, "scarica_fotogramma", _scarica)
    adesso = _T + timedelta(days=8)
    primo = await archivia(tmp_path, giorni=9, massimo=10_000, adesso=adesso)
    assert primo["persi"] == 2  # CUM3 e SRT1 delle 00 di otto giorni fa
    chiesti.clear()
    await archivia(tmp_path, giorni=9, massimo=10_000, adesso=adesso)
    assert chiesti == []


async def test_lo_sweep_scarica_prima_le_ore_recenti(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chiesti: list[tuple[str, datetime]] = []

    async def _scarica(prodotto: str, t: datetime) -> bytes:
        chiesti.append((prodotto, t))
        return b"tif"

    monkeypatch.setattr(merging_archive, "scarica_fotogramma", _scarica)
    adesso = _T + timedelta(hours=8)
    await archivia(tmp_path, giorni=1, massimo=1, adesso=adesso, recenti_prima=True)
    assert chiesti == [("CUM3", _T + timedelta(hours=6))]


async def test_archivia_si_ferma_al_tetto(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _scarica(prodotto: str, t: datetime) -> bytes:
        return b"tif"

    monkeypatch.setattr(merging_archive, "scarica_fotogramma", _scarica)
    conti = await archivia(tmp_path, giorni=2, massimo=5, adesso=_T)
    assert conti["scaricati"] == 5


def _tif(path: Path, valore: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=5,
        height=5,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(15.0, 38.0, 0.01, 0.01),
        nodata=-9999.0,
    ) as ds:
        ds.write(np.full((1, 5, 5), valore, dtype=np.float32))


def test_le_ore_del_blocco_sommano_al_merging(tmp_path: Path) -> None:
    fine = _T + timedelta(hours=3)
    _tif(percorso(tmp_path, "CUM3", fine), 60.0)
    for k, mm in ((2, 1.0), (1, 2.0), (0, 1.0)):
        _tif(percorso(tmp_path, "SRT1", fine - timedelta(hours=k)), mm)
    ore = MergingArchive(tmp_path).oraria([(15.02, 37.98)], _T, fine)
    assert [ore[_T + timedelta(hours=h)][0] for h in (1, 2, 3)] == [15.0, 30.0, 15.0]


def test_senza_file_l_ora_non_e_misurata(tmp_path: Path) -> None:
    ore = MergingArchive(tmp_path).oraria([(15.02, 37.98)], _T, _T + timedelta(hours=3))
    assert {v[0] for v in ore.values()} == {None}


def test_un_file_corrotto_e_un_ora_non_misurata(tmp_path: Path) -> None:
    file = percorso(tmp_path, "CUM3", _T + timedelta(hours=3))
    file.parent.mkdir(parents=True)
    file.write_bytes(b"<Error>AccessDenied</Error>")
    ore = MergingArchive(tmp_path).oraria([(15.02, 37.98)], _T, _T + timedelta(hours=3))
    assert {v[0] for v in ore.values()} == {None}
