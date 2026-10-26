"""``limen fetch-static`` (#305): scarica ciò che manca, verifica ciò che c'è."""

from __future__ import annotations

import contextlib
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from limen.cli import fetch_static


@pytest.fixture
def radice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("LIMEN_DATA_ROOT", str(tmp_path))
    monkeypatch.delenv("LIMEN_IMPERVIOUSNESS_DEST", raising=False)

    @contextlib.asynccontextmanager
    async def pool(*_a: Any) -> AsyncIterator[None]:
        yield

    monkeypatch.setattr(fetch_static, "lifespan_pool", pool)
    return tmp_path


@pytest.fixture
def scaricati(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Download ed estrazioni finti: si conta chi viene chiamato."""
    chiamate: list[str] = []

    async def imperv(**_: Any) -> Path:
        dest = fetch_static._resolve_dest(None)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"tif")
        chiamate.append("imperviousness")
        return dest

    async def scarica(url: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"pbf")
        chiamate.append("pbf")

    def estrai(_pbf: Path, dest: Path, where: str) -> None:
        dest.write_text(where)
        chiamate.append(dest.name)

    monkeypatch.setattr(fetch_static, "fetch_imperviousness", imperv)
    monkeypatch.setattr(fetch_static, "_scarica", scarica)
    monkeypatch.setattr(fetch_static, "_estrai", estrai)
    return chiamate


async def test_scarica_quello_che_manca_e_poi_niente(radice: Path, scaricati: list[str]) -> None:
    assert await fetch_static.run() == 0
    assert scaricati == ["imperviousness", "pbf", "osm_roads.gpkg", "osm_rails.gpkg"]
    manifest = json.loads((radice / fetch_static.MANIFEST).read_text())
    assert set(manifest) == {
        "sealing/clms_imd_2018/imd_2018_100m.tif",
        "osm/osm_roads.gpkg",
        "osm/osm_rails.gpkg",
    }
    assert manifest["osm/osm_rails.gpkg"]["byte"] == len("railway = 'rail'")

    scaricati.clear()
    assert await fetch_static.run() == 0
    assert scaricati == []


async def test_un_file_alterato_ferma_il_comando(radice: Path, scaricati: list[str]) -> None:
    assert await fetch_static.run() == 0
    (radice / "osm" / "osm_roads.gpkg").write_text("troncato")
    scaricati.clear()
    assert await fetch_static.run() == 1
    assert scaricati == []


async def test_i_file_gia_presenti_si_registrano_senza_riscaricarli(
    radice: Path, scaricati: list[str]
) -> None:
    """Estratti prima con `make osm-data`: da qui in poi si verificano."""
    (radice / "osm").mkdir()
    for nome in fetch_static.OSM_ESTRATTI:
        (radice / "osm" / nome).write_text("di prima")
    assert await fetch_static.run() == 0
    assert scaricati == ["imperviousness"]
    manifest = json.loads((radice / fetch_static.MANIFEST).read_text())
    assert "osm/osm_roads.gpkg" in manifest
