"""EGMS Ortho L3: tile, download e statistiche per cella."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from limen.integrations.egms import client
from limen.integrations.egms.aggregate import Cella, Griglia, mosaico, per_cella


def test_le_tile_sono_le_centinaia_di_km_dell_angolo() -> None:
    assert client.tile_per_limiti(4_750_000, 1_950_000, 4_760_000, 1_960_000) == [(47, 19)]
    assert client.tile_per_limiti(4_790_000, 1_990_000, 4_810_000, 2_010_000) == [
        (47, 19),
        (47, 20),
        (48, 19),
        (48, 20),
    ]
    assert client.nome((47, 19), "U", "2020_2024") == "EGMS_L3_E47N19_100km_U_2020_2024_1"


def _griglia(verticale: list[list[float]], est: list[list[float]]) -> Griglia:
    return Griglia(
        verticale=np.array(verticale, dtype="float32"),
        est=np.array(est, dtype="float32"),
        left=0.0,
        top=400.0,
    )


def test_la_cella_prende_i_pixel_col_centro_dentro() -> None:
    nan = float("nan")
    # 4 x 4 pixel da 100 m; la cella (100..300, 100..300) contiene i centri
    # delle colonne 1-2 e delle righe 1-2.
    v = [[9, 9, 9, 9], [9, 1, 2, 9], [9, 3, nan, 9], [9, 9, 9, 9]]
    e = [[9, 9, 9, 9], [9, 0, 0, 9], [9, 4, 1, 9], [9, 9, 9, 9]]
    (r,) = per_cella([Cella("c", 100.0, 100.0, 300.0, 300.0)], _griglia(v, e))
    assert r.scatterer_count == 3
    assert r.velocita_verticale_mmy == pytest.approx(2.0)
    assert r.velocita_est_mmy == pytest.approx(0.0)
    # moduli 1, 2, 5: il 90° percentile sta verso il pixel che si muove.
    assert r.insar_velocity_mmy == pytest.approx(np.percentile([1.0, 2.0, 5.0], 90))


def test_una_cella_senza_pixel_validi_non_e_ferma() -> None:
    nan = float("nan")
    v = [[nan, nan], [nan, nan]]
    (r,) = per_cella([Cella("c", 0.0, 200.0, 200.0, 400.0)], _griglia(v, v))
    assert r.scatterer_count == 0
    assert r.insar_velocity_mmy is None
    assert r.velocita_verticale_mmy is None


def test_una_cella_fuori_dalla_griglia_non_alza() -> None:
    v = [[1.0]]
    (r,) = per_cella([Cella("c", 5000.0, 5000.0, 6000.0, 6000.0)], _griglia(v, v))
    assert r.scatterer_count == 0


def _tiff(path: Path, left: float, top: float, dati: list[list[float]]) -> None:
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin

    arr = np.array(dati, dtype="float32")
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=arr.shape[0],
        width=arr.shape[1],
        count=1,
        dtype="float32",
        crs="EPSG:3035",
        transform=from_origin(left, top, 100.0, 100.0),
        nodata=-9999.0,
    ) as dst:
        dst.write(arr, 1)


def test_il_mosaico_cuce_due_tile_e_lascia_nan_dove_mancano(tmp_path: Path) -> None:
    a, b = tmp_path / "a.tiff", tmp_path / "b.tiff"
    _tiff(a, 0.0, 200.0, [[1, 2], [3, -9999]])
    _tiff(b, 200.0, 200.0, [[5, 6], [7, 8]])
    m = mosaico([a, b], minx=0.0, miny=0.0, maxx=500.0, maxy=200.0)
    assert m.shape == (2, 5)
    assert m[0, :4].tolist() == [1, 2, 5, 6]
    assert np.isnan(m[1, 1])
    assert np.isnan(m[:, 4]).all()


class _Risposta:
    def __init__(self, status: int, content: bytes = b"") -> None:
        self.status_code = status
        self.content = content


def _zip(base: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"{base}.csv", "pid,mean_velocity\n")
        z.writestr(f"{base}.tiff", b"TIFF")
    return buf.getvalue()


async def test_scarica_tiene_solo_il_tiff_e_ricorda_le_tile_assenti(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chieste: list[str] = []

    async def _fetch(_m: str, url: str, **kw: Any) -> _Risposta:
        chieste.append(url)
        assert kw["params"] == {"id": "t"}
        return _Risposta(404) if "E40N15" in url else _Risposta(200, _zip(url.split("/")[-1][:-4]))

    monkeypatch.setattr(client, "fetch_with_retry", _fetch)
    args = {"release": "2020_2024", "url": "https://x/download", "token": "t"}

    p = await client.scarica_tile(tmp_path, (47, 19), "U", **args)
    assert p is not None and p.read_bytes() == b"TIFF"
    assert await client.scarica_tile(tmp_path, (40, 15), "U", **args) is None
    # Il secondo giro non richiede niente: tiff presente, mare ricordato.
    await client.scarica_tile(tmp_path, (47, 19), "U", **args)
    await client.scarica_tile(tmp_path, (40, 15), "U", **args)
    assert len(chieste) == 2
    assert sorted(f.suffix for f in tmp_path.iterdir()) == [".assente", ".tiff"]


async def test_un_token_scaduto_alza(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fetch(_m: str, _url: str, **_kw: Any) -> _Risposta:
        return _Risposta(401)

    monkeypatch.setattr(client, "fetch_with_retry", _fetch)
    with pytest.raises(RuntimeError, match="401"):
        await client.scarica_tile(
            tmp_path, (47, 19), "U", release="2020_2024", url="https://x", token="t"
        )
