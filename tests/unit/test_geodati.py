"""I dati di base ISPRA per GeoServer, e il retry comune per i download in streaming."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import httpx
import pytest

from limen.config.settings import GeodatiSettings
from limen.integrations._http import SharedHttpClient, call_with_retry
from limen.integrations.idrogeo import geodati


@pytest.fixture(autouse=True)
def _senza_dati_base(monkeypatch: pytest.MonkeyPatch) -> None:
    """ISTAT, CORINE e geolitologia hanno i loro test (test_geoserver_dati_base)."""

    async def niente(*_a: object) -> tuple[list[str], dict[str, str]]:
        return [], {}

    monkeypatch.setattr(geodati, "sync_dati_base", niente)


def _zip(nome: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr(f"{nome}.shp", b"SHP")
    return buffer.getvalue()


def _risposta(stato: int) -> httpx.Response:
    return httpx.Response(stato, request=httpx.Request("GET", "https://x"))


async def test_il_retry_riprova_un_503_ma_non_un_404() -> None:
    chiamate: list[int] = []

    async def occupato_poi_ok() -> str:
        chiamate.append(1)
        if len(chiamate) == 1:
            _risposta(503).raise_for_status()
        return "ok"

    assert await call_with_retry(occupato_poi_ok) == "ok"
    assert len(chiamate) == 2

    chiamate.clear()

    async def manca() -> str:
        chiamate.append(1)
        _risposta(404).raise_for_status()
        return "mai"

    with pytest.raises(httpx.HTTPStatusError):
        await call_with_retry(manca)
    assert len(chiamate) == 1


def test_i_file_sono_quelli_che_legge_geoserver_source() -> None:
    nomi = [d.filename for d in geodati.dataset()]
    assert len(nomi) == 5 * 21 + 2
    # Regione per regione, con i nomi delle tabelle che il loader cerca.
    assert "frane_piff_puglia_opendata.zip" in nomi
    assert "frane_poly_bolzano_opendata.zip" in nomi
    assert not any("_ispra_opendata" in n for n in nomi)
    assert "Mosaicatura_ISPRA_2020_aree_pericolosita_idraulica.zip" in nomi


def test_la_cartella_e_quella_di_geoserver_init(monkeypatch: pytest.MonkeyPatch) -> None:
    from limen.config.percorsi import cartella_geoserver

    monkeypatch.delenv("GEOSERVER_SHAPEFILE_DIR", raising=False)
    monkeypatch.setenv("LIMEN_DATA_ROOT", "/dati")
    assert cartella_geoserver() == Path("/dati/geoserver")
    monkeypatch.setenv("GEOSERVER_SHAPEFILE_DIR", "/gs")
    assert cartella_geoserver() == Path("/gs")


async def test_il_secondo_giro_chiede_solo_se_e_cambiato(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    richieste: list[httpx.Request] = []

    def idrogeo(request: httpx.Request) -> httpx.Response:
        richieste.append(request)
        nome = request.url.path.rsplit("/", 1)[1]
        if nome == "frane_line_molise_opendata.zip":
            return httpx.Response(404)  # un file che manca non ferma gli altri
        if request.headers.get("if-none-match") == '"v1"':
            return httpx.Response(304)
        return httpx.Response(
            200, content=_zip(nome.removesuffix(".zip")), headers={"ETag": '"v1"'}
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(idrogeo))

    async def _get(_cls: type[SharedHttpClient]) -> httpx.AsyncClient:
        return client

    monkeypatch.setattr(SharedHttpClient, "get", classmethod(_get))
    monkeypatch.setenv("GEOSERVER_SHAPEFILE_DIR", str(tmp_path))
    impostazioni = GeodatiSettings(rivalida_dopo_giorni=0)

    primo = await geodati.sync_geodati(impostazioni)
    assert len(primo.cambiati) == 106
    assert list(primo.falliti) == ["frane_line_molise_opendata.zip"]
    shp = tmp_path / "frane_piff_puglia_opendata" / "frane_piff_puglia_opendata.shp"
    assert shp.read_bytes() == b"SHP"

    richieste.clear()
    secondo = await geodati.sync_geodati(impostazioni)
    assert secondo.cambiati == [] and secondo.invariati == 106
    condizionali = [r for r in richieste if "frane_line_molise" not in r.url.path]
    assert len(condizionali) == 106
    assert all(r.headers.get("if-none-match") == '"v1"' for r in condizionali)
    assert not list(tmp_path.glob("*.part"))


async def test_un_file_recente_non_si_chiede_e_uno_rotto_si_riscarica(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    richieste: list[str] = []
    rotto = [True]

    def idrogeo(request: httpx.Request) -> httpx.Response:
        nome = request.url.path.rsplit("/", 1)[1]
        richieste.append(nome)
        if nome == "dgpv_poly_puglia_opendata.zip" and rotto:
            rotto.clear()
            return httpx.Response(200, content=b"<html>non uno zip</html>", headers={"ETag": '"x"'})
        return httpx.Response(200, content=_zip("a"), headers={"ETag": '"v1"'})

    client = httpx.AsyncClient(transport=httpx.MockTransport(idrogeo))

    async def _get(_cls: type[SharedHttpClient]) -> httpx.AsyncClient:
        return client

    monkeypatch.setattr(SharedHttpClient, "get", classmethod(_get))
    monkeypatch.setenv("GEOSERVER_SHAPEFILE_DIR", str(tmp_path))
    impostazioni = GeodatiSettings(rivalida_dopo_giorni=30)

    primo = await geodati.sync_geodati(impostazioni)
    assert list(primo.falliti) == ["dgpv_poly_puglia_opendata.zip"]
    # Lo ZIP rotto e il suo ETag sono andati: niente 304 eterno.
    assert not (tmp_path / "dgpv_poly_puglia_opendata.zip").exists()
    assert not (tmp_path / "dgpv_poly_puglia_opendata.zip.meta.json").exists()

    richieste.clear()
    secondo = await geodati.sync_geodati(impostazioni)
    # Gli altri 106 sono recenti: si chiede solo quello che mancava.
    assert richieste == ["dgpv_poly_puglia_opendata.zip"]
    assert secondo.cambiati == ["dgpv_poly_puglia_opendata.zip"]
    assert secondo.invariati == 106 and not secondo.falliti
