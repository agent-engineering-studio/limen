from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest
from firms_client.landcover import WORLDCOVER_URL

from limen.integrations.firms import worldcover as wc


def test_the_tiles_over_italy() -> None:
    tiles = wc.worldcover_tiles((6.0, 35.0, 19.0, 48.0))
    assert len(tiles) == 25  # 5 rows (33-45 N) x 5 columns (6-18 E)
    assert tiles[0].endswith("/v200/2021/map/ESA_WorldCover_10m_2021_v200_N33E006_Map.tif")
    assert tiles[-1].endswith("_N45E018_Map.tif")


def _run(handler: httpx.MockTransport, cartella: Path) -> wc.Esito:
    async def go() -> wc.Esito:
        async with httpx.AsyncClient(transport=handler) as client:
            return await wc.scarica_worldcover(cartella, client=client)

    return asyncio.run(go())


def test_download_skip_and_the_sea(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        wc,
        "worldcover_tiles",
        lambda bbox: [f"{WORLDCOVER_URL}/v200/2021/map/{n}" for n in ("A.tif", "SEA.tif")],
    )
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("SEA.tif"):
            return httpx.Response(404)
        return httpx.Response(200, content=b"tiff")

    cartella = tmp_path / "worldcover"
    esito = _run(httpx.MockTransport(handler), cartella)
    assert esito.scaricate == ["A.tif"] and esito.assenti == ["SEA.tif"] and not esito.fallite
    assert (cartella / "v200/2021/map/A.tif").read_bytes() == b"tiff"
    assert not list(tmp_path.rglob("*.part"))
    assert wc.worldcover_locale(cartella) is not None

    calls.clear()
    again = _run(httpx.MockTransport(handler), cartella)
    assert again.presenti == ["A.tif"] and calls == ["/v200/2021/map/SEA.tif"]


def test_a_failed_tile_is_reported_and_leaves_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(wc, "worldcover_tiles", lambda bbox: [f"{WORLDCOVER_URL}/x/B.tif"])
    esito = _run(httpx.MockTransport(lambda r: httpx.Response(400)), tmp_path / "worldcover")
    assert esito.fallite == ["B.tif"] and not list(tmp_path.rglob("*.*"))
    assert wc.worldcover_locale(tmp_path / "worldcover") is None


def test_the_folder_must_be_named_as_the_library_reads_it(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="worldcover"):
        _run(httpx.MockTransport(lambda r: httpx.Response(200)), tmp_path / "tiles")


def test_the_folder_is_firms_client_s(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    assert wc.cartella_worldcover() == tmp_path / "firms-client" / "worldcover"
