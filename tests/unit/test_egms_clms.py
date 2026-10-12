"""La chiave di servizio CLMS: JWT, token, ricerca, release nuova."""

from __future__ import annotations

import base64
import json
from typing import Any

import pytest

from limen.config.settings import EgmsSettings, Settings
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


def _parte(jwt: str, i: int) -> dict[str, Any]:
    pezzo = jwt.split(".")[i]
    return dict(json.loads(base64.urlsafe_b64decode(pezzo + "=" * (-len(pezzo) % 4))))


def test_il_jwt_e_quello_che_chiede_il_clms() -> None:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    chiave = _chiave()
    jwt = clms.asserzione(chiave, adesso=1000)
    assert _parte(jwt, 0) == {"alg": "RS256", "typ": "JWT"}
    assert _parte(jwt, 1) == {
        "iss": "c",
        "sub": "u",
        "aud": chiave["token_uri"],
        "iat": 1000,
        "exp": 4600,
    }
    testa, corpo, firma = jwt.split(".")
    privata = serialization.load_pem_private_key(chiave["private_key"].encode(), password=None)
    assert isinstance(privata, rsa.RSAPrivateKey)
    privata.public_key().verify(
        base64.urlsafe_b64decode(firma + "=" * (-len(firma) % 4)),
        f"{testa}.{corpo}".encode(),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )


def test_una_chiave_incompleta_non_e_una_chiave() -> None:
    assert clms.leggi_chiave("") is None
    assert clms.leggi_chiave(json.dumps({"client_id": "c"})) is None
    assert clms.leggi_chiave(json.dumps(_chiave())) is not None


class _Risposta:
    def __init__(self, status: int, dati: Any) -> None:
        self.status_code = status
        self._dati = dati

    def json(self) -> Any:
        return self._dati


@pytest.fixture
def archivio(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, Any]]:
    chiamate: list[tuple[str, str, Any]] = []

    async def _fetch(metodo: str, url: str, **kw: Any) -> _Risposta:
        chiamate.append((metodo, url, kw.get("json")))
        if url.endswith("oauth2-token"):
            return _Risposta(200, {"access_token": "a", "expires_in": 3600})
        assert kw["headers"]["Authorization"] == "Bearer a"
        if url.endswith("/releases"):
            return _Risposta(200, ["2019-2023", "2020-2024", "2021-2025"])
        if url.endswith("/search"):
            tile = kw["json"]["tileId"]
            if tile == "E40N15":
                return _Risposta(200, {"status": False, "message": "Invalid tile ID: 'E40N15'"})
            if tile == "E99N99":
                return _Risposta(200, {"status": False, "message": "Please log in"})
            return _Risposta(
                200, {"status": True, "id": "q", "hits": [{}] if tile == "E47N19" else []}
            )
        raise AssertionError(url)

    monkeypatch.setattr(clms, "fetch_with_retry", _fetch)
    return chiamate


async def test_la_ricerca_usa_un_token_solo_e_dice_se_la_tile_c_e(
    archivio: list[tuple[str, str, Any]],
) -> None:
    s = clms.Sessione(_chiave(), archivio="https://a/archive")
    assert await s.cerca((47, 19), "U", "2020_2024") == "q"
    assert await s.cerca((40, 15), "E", "2020_2024") is None  # mare: «Invalid tile ID»
    assert await s.cerca((48, 19), "E", "2020_2024") is None  # nessun risultato
    with pytest.raises(RuntimeError, match="log in"):
        await s.cerca((99, 99), "E", "2020_2024")
    assert [u for _, u, _ in archivio].count("https://land.example/@@oauth2-token") == 1
    corpo = archivio[1][2]
    assert corpo == {
        "tileId": "E47N19",
        "releases": ["2020-2024"],
        "levels": ["L3"],
        "productType": "ORTHO-UP",
    }
    assert archivio[2][2]["productType"] == "ORTHO-EAST"


async def test_una_release_nuova_si_segnala(archivio: list[tuple[str, str, Any]]) -> None:
    from pydantic import SecretStr

    s = Settings(egms=EgmsSettings(service_key=SecretStr(json.dumps(_chiave()))))
    esito = await sync_job.controlla_release(s)
    assert esito == {
        "status": "nuova_release",
        "configurata": "2020-2024",
        "disponibile": "2021-2025",
    }


async def test_senza_chiave_il_controllo_si_salta() -> None:
    esito = await sync_job.controlla_release(Settings(egms=EgmsSettings()))
    assert esito["status"] == "skipped"
