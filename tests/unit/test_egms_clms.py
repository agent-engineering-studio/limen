"""La chiave di servizio CLMS e l'archivio EGMS visti da Limen."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pytest
from pydantic import SecretStr

from limen.config.settings import EgmsSettings, Settings
from limen.integrations._http import SharedHttpClient
from limen.integrations.egms import clms, sync_job


def _chiave() -> dict[str, Any]:
    pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    privata = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = privata.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()
    return {
        "client_id": "c",
        "user_id": "u",
        "private_key": pem,
        "token_uri": "https://land.example/@@oauth2-token",
    }


def test_una_chiave_incompleta_non_e_una_chiave() -> None:
    assert clms.leggi_chiave("") is None
    assert clms.leggi_chiave(json.dumps({"client_id": "c"})) is None
    assert clms.leggi_chiave(json.dumps(_chiave())) is not None


def test_la_chiave_viene_dalla_variabile_o_dal_file(tmp_path: Path) -> None:
    testo = json.dumps(_chiave())
    assert clms.chiave(EgmsSettings(service_key=SecretStr(testo))) is not None
    file = tmp_path / "chiave.json"
    file.write_text(testo)
    assert clms.chiave(EgmsSettings(service_key_file=str(file))) is not None
    assert EgmsSettings(service_key_file=str(file)).attivo
    assert clms.chiave(EgmsSettings(service_key_file=str(tmp_path / "manca.json"))) is None
    assert clms.chiave(EgmsSettings()) is None


def test_il_motivo_del_salto_e_detto() -> None:
    assert "non è più supportato" in clms.perche_no(EgmsSettings(token=SecretStr("abc")))
    assert "illeggibile" in clms.perche_no(EgmsSettings(service_key=SecretStr("{}")))
    assert clms.perche_no(EgmsSettings()).startswith("né")


class _Archivio:
    """Un archivio finto: token, release, ricerca per tile, download."""

    def __init__(self) -> None:
        self.richieste: list[httpx.Request] = []
        self.csv = (
            b"pid,easting,northing,height_ortho,mean_velocity,acceleration,seasonality,20200101\n"
            b"a,4700050,1999950,10,1.0,0.5,3.0,0.0\n"
            b"b,4700150,1999950,10,1.0,-0.2,1.5,0.0\n"
        )

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.richieste.append(request)
        path = request.url.path
        if path.endswith("oauth2-token"):
            return httpx.Response(200, json={"access_token": "a", "expires_in": 3600})
        if path.endswith("/releases"):
            # Dopo la 2020-2024 è uscita la 2020-2025, non la 2021-2025.
            return httpx.Response(200, json=["2019-2023", "2020-2024", "2020-2025"])
        if path.endswith("/search"):
            assert request.headers["Authorization"] == "Bearer a"
            tile = json.loads(request.content)["tileId"]
            if tile != "E47N19":
                return httpx.Response(
                    200, json={"status": False, "message": f"Invalid tile ID: '{tile}'"}
                )
            trovata = {
                "filename": "EGMS_L3_E47N19_100km_U_2020_2024_1.zip",
                "version": "2020_2024_1",
            }
            return httpx.Response(200, json={"status": True, "id": "q", "hits": [trovata]})
        if "/download/" in path:
            assert request.url.params["id"] == "q"
            stem = path.rsplit("/", 1)[1].removesuffix(".zip")
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as z:
                z.writestr(f"{stem}.tiff", b"TIFF")
                z.writestr(f"{stem}.csv", self.csv)
            return httpx.Response(200, content=buffer.getvalue())
        raise AssertionError(path)

    def scaricati(self) -> int:
        return sum("/download/" in r.url.path for r in self.richieste)


@pytest.fixture
def archivio(monkeypatch: pytest.MonkeyPatch) -> _Archivio:
    finto = _Archivio()
    client = httpx.AsyncClient(transport=httpx.MockTransport(finto))

    async def _get(_cls: type[SharedHttpClient]) -> httpx.AsyncClient:
        return client

    monkeypatch.setattr(SharedHttpClient, "get", classmethod(_get))
    return finto


def _impostazioni(**kw: Any) -> EgmsSettings:
    return EgmsSettings(
        service_key=SecretStr(json.dumps(_chiave())), archive_url="https://a/archive", **kw
    )


async def test_le_tile_si_scaricano_una_volta_sola(archivio: _Archivio, tmp_path: Path) -> None:
    a = await clms.archivio(_impostazioni())
    assert a is not None
    tiff = await a.fetch_tile((47, 19), "U", "2020_2024", tmp_path)
    assert tiff is not None and tiff.read_bytes() == b"TIFF"
    assert await a.fetch_tile((40, 15), "U", "2020_2024", tmp_path) is None  # mare
    # Il secondo giro non chiede niente: il tiff c'è, il mare è ricordato.
    prima = len(archivio.richieste)
    assert await a.fetch_tile((47, 19), "U", "2020_2024", tmp_path) == tiff
    assert await a.fetch_tile((40, 15), "U", "2020_2024", tmp_path) is None
    assert len(archivio.richieste) == prima
    assert archivio.scaricati() == 1
    assert not list(tmp_path.glob("*.zip")) and not list(tmp_path.glob("*.part"))


async def test_una_release_nuova_si_segnala(archivio: _Archivio) -> None:
    vecchia = Settings(egms=_impostazioni(release="2020_2024"))
    assert await sync_job.controlla_release(vecchia) == {
        "status": "nuova_release",
        "configurata": "2020-2024",
        "disponibile": "2020-2025",
    }
    assert (await sync_job.controlla_release(Settings(egms=_impostazioni())))["status"] == "ok"


async def test_senza_chiave_il_controllo_si_salta() -> None:
    esito = await sync_job.controlla_release(Settings(egms=EgmsSettings()))
    assert esito["status"] == "skipped"


def test_i_segnaposto_vecchi_del_mare_si_rinominano(tmp_path: Path) -> None:
    (tmp_path / "EGMS_L3_E40N15_100km_U_2020_2025_1.assente").touch()
    (tmp_path / "EGMS_L3_E40N16_100km_E_2020_2025.assente").touch()
    (tmp_path / "EGMS_L3_E41N15_100km_U_2020_2025_absent").touch()
    (tmp_path / "EGMS_L3_E41N15_100km_U_2020_2025_1.assente").touch()  # già migrato
    (tmp_path / "altro.assente").touch()
    assert sync_job.migra_segnaposto(tmp_path) == 3
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "EGMS_L3_E40N15_100km_U_2020_2025_absent",
        "EGMS_L3_E40N16_100km_E_2020_2025_absent",
        "EGMS_L3_E41N15_100km_U_2020_2025_absent",
        "altro.assente",
    ]
    assert sync_job.migra_segnaposto(tmp_path) == 0


async def test_una_tile_in_mare_migrata_non_chiede_niente(
    archivio: _Archivio, tmp_path: Path
) -> None:
    (tmp_path / "EGMS_L3_E40N15_100km_U_2020_2024_1.assente").touch()
    sync_job.migra_segnaposto(tmp_path)
    a = await clms.archivio(_impostazioni())
    assert a is not None
    assert await a.fetch_tile((40, 15), "U", "2020_2024", tmp_path) is None
    assert archivio.richieste == []


async def test_le_tile_in_parallelo_usano_un_token_solo(
    archivio: _Archivio, tmp_path: Path
) -> None:
    import asyncio

    a = await clms.archivio(_impostazioni())
    assert a is not None
    tile = [(47, 19), (40, 15), (41, 15), (42, 15)]
    trovate = await asyncio.gather(*(a.fetch_tile(t, "U", "2020_2024", tmp_path) for t in tile))
    assert [p is not None for p in trovate] == [True, False, False, False]
    token = [r for r in archivio.richieste if r.url.path.endswith("oauth2-token")]
    assert len(token) == 1


@pytest.mark.parametrize("valore", [0, 3])
def test_la_concorrenza_resta_fra_1_e_2(valore: int) -> None:
    # 0 bloccherebbe il sync per sempre; oltre 2 l'archivio risponde 429.
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        EgmsSettings(concorrenza=valore)
    assert EgmsSettings(concorrenza=1).concorrenza == 1


async def test_il_download_passa_dal_retry_di_limen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Un 429 («At most 2 downloads») e poi la tile: lo riprova la policy di
    # `_http`, non un retry del pacchetto.
    finto = _Archivio()
    occupato = [True]

    def _prima_429(request: httpx.Request) -> httpx.Response:
        if "/download/" in request.url.path and occupato:
            occupato.clear()
            finto.richieste.append(request)
            return httpx.Response(429, text="At most 2 downloads may be performed simultaneously")
        return finto(request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(_prima_429))

    async def _get(_cls: type[SharedHttpClient]) -> httpx.AsyncClient:
        return client

    monkeypatch.setattr(SharedHttpClient, "get", classmethod(_get))
    a = await clms.archivio(_impostazioni())
    assert a is not None
    tiff = await a.fetch_tile((47, 19), "U", "2020_2024", tmp_path)
    assert tiff is not None and tiff.read_bytes() == b"TIFF"
    assert finto.scaricati() == 2
    assert not list(tmp_path.glob("*.part"))


async def test_gli_attributi_vengono_dallo_stesso_zip(archivio: _Archivio, tmp_path: Path) -> None:
    a = await clms.archivio(_impostazioni())
    assert a is not None
    # Una tile scaricata prima della #380: c'è il GeoTIFF, mancano gli attributi.
    vecchia = await a.fetch_tile((47, 19), "U", "2020_2024", tmp_path)
    assert vecchia is not None and not clms.attributi_di(vecchia).exists()
    tiff = await a.fetch_tile((47, 19), "U", "2020_2024", tmp_path, attributi=True)
    assert tiff == vecchia
    with np.load(clms.attributi_di(tiff)) as attr:
        assert attr["acceleration"].tolist() == [0.5, -0.2]
        assert attr["seasonality"].tolist() == [3.0, 1.5]
        assert attr["easting"].tolist() == [4700050, 4700150]
    # Ora c'è tutto: nessun altro download.
    assert await a.fetch_tile((47, 19), "U", "2020_2024", tmp_path, attributi=True) == tiff
    assert archivio.scaricati() == 2
    assert not list(tmp_path.glob("*.csv")) and not list(tmp_path.glob("*.part"))


async def test_un_csv_senza_colonne_lascia_attributi_vuoti(
    archivio: _Archivio, tmp_path: Path
) -> None:
    archivio.csv = b"pid,easting,northing,mean_velocity\na,1,2,3\n"
    a = await clms.archivio(_impostazioni())
    assert a is not None
    tiff = await a.fetch_tile((47, 19), "U", "2020_2024", tmp_path, attributi=True)
    assert tiff is not None
    with np.load(clms.attributi_di(tiff)) as attr:
        assert attr["acceleration"].size == 0
    assert await a.fetch_tile((47, 19), "U", "2020_2024", tmp_path, attributi=True) == tiff
    assert archivio.scaricati() == 1
