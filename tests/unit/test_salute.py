"""La pagina «Salute» (#408): fonti esterne, cause dei «non misurati», passi del notturno."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from limen.core import salute as regole
from limen.core.models.hazard import HazardType
from limen.data.repos.job_runs_repo import JobRun
from limen.integrations import _http, salute

_T = datetime(2026, 11, 3, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _registro_vuoto(monkeypatch: pytest.MonkeyPatch) -> None:
    salute.svuota()
    monkeypatch.setattr(salute, "_host_open_meteo_locali", lambda: frozenset({"openmeteo"}))


@pytest.mark.parametrize(
    ("url", "fonte"),
    [
        ("http://openmeteo:8080/v1/forecast", "openmeteo_locale"),
        ("https://api.open-meteo.com/v1/forecast", "openmeteo"),
        ("https://flood-api.open-meteo.com/v1/flood", "glofas"),
        ("https://radar-api.protezionecivile.it/wide/product", "dpc"),
        ("https://maps.effis.emergency.copernicus.eu/gwis", "effis"),
        ("https://firms.modaps.eosdis.nasa.gov/api/area", "firms"),
        ("https://webservices.ingv.it/fdsnws/event/1/query", "ingv"),
        ("https://news.google.com/rss", None),
    ],
)
def test_la_fonte_si_riconosce_dall_host(url: str, fonte: str | None) -> None:
    assert salute.fonte_di(url) == fonte


async def test_un_429_persistente_finisce_nel_registro() -> None:
    """Il 3 novembre Open-Meteo pubblico ha risposto 429 per ore: lo dicevano solo i log."""

    def _risponde(req: httpx.Request) -> httpx.Response:
        return httpx.Response(429, request=req)

    async with httpx.AsyncClient(transport=httpx.MockTransport(_risponde)) as cli:
        with pytest.raises(httpx.HTTPStatusError):
            await _http.fetch_with_retry(
                "GET", "https://api.open-meteo.com/v1/forecast", client=cli
            )
    esito = salute.svuota()["openmeteo"]
    assert esito.ultimo_ok is None
    assert esito.errore is not None and "429" in esito.errore
    assert salute.svuota() == {}


async def test_una_risposta_buona_e_un_404_non_sono_errori_della_fonte() -> None:
    def _risponde(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404 if "scaduto" in req.url.path else 200, request=req)

    async with httpx.AsyncClient(transport=httpx.MockTransport(_risponde)) as cli:
        await _http.fetch_with_retry("GET", "https://radar-api.protezionecivile.it/ok", client=cli)
        await _http.fetch_with_retry(
            "GET", "https://radar-api.protezionecivile.it/scaduto", client=cli
        )
    esito = salute.svuota()["dpc"]
    assert esito.ultimo_ok is not None
    assert esito.ultimo_errore is None


async def test_una_fonte_irraggiungibile_si_annota() -> None:
    def _risponde(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("rifiutata", request=req)

    async with httpx.AsyncClient(transport=httpx.MockTransport(_risponde)) as cli:
        with pytest.raises(httpx.ConnectError):
            await _http.fetch_with_retry("GET", "http://openmeteo:8080/v1/forecast", client=cli)
    assert "ConnectError" in (salute.svuota()["openmeteo_locale"].errore or "")


def test_in_errore_e_l_ultimo_esito() -> None:
    assert regole.in_errore(None, _T)
    assert regole.in_errore(_T - timedelta(hours=1), _T)
    assert not regole.in_errore(_T, _T - timedelta(hours=1))
    assert not regole.in_errore(None, None)


def test_la_causa_e_una_fonte_da_cui_il_pericolo_dipende() -> None:
    assert regole.cause(HazardType.WILDFIRE, ["glofas", "openmeteo"]) == ["Open-Meteo pubblico"]
    assert regole.cause(HazardType.FLOOD, ["glofas"]) == [
        "GloFAS via Open-Meteo (portata dei fiumi)"
    ]
    assert regole.cause(HazardType.LANDSLIDE, ["firms"]) == []


def _run(status: str, metrics: dict[str, Any], *, error: str | None = None) -> JobRun:
    return JobRun(1, "limen-nightly", "backup", _T, _T, status, metrics, error, "w")


def test_i_passi_del_notturno_si_leggono_senza_segreti() -> None:
    assert regole.passo(_run("ok", {"chiave": "x"})) == ("ok", None)
    assert regole.passo(_run("skipped", {"reason": "BACKUP__BUCKET non impostato"})) == (
        "saltato",
        "BACKUP__BUCKET non impostato",
    )
    assert regole.passo(_run("ok", {"status": "error", "error_type": "OSError"})) == (
        "errore",
        "OSError",
    )
    assert regole.passo(_run("ok", {"avviso": True, "avvisi": ["crollo del 60%"]})) == (
        "avviso",
        "crollo del 60%",
    )


def test_l_endpoint_dice_la_fonte_guasta_e_il_pericolo_che_ne_risente(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from limen.api.endpoints import installazione as ep
    from limen.config.settings import Settings
    from limen.data.repos.salute_repo import Misurate, RigaFonte

    async def _fonti() -> list[RigaFonte]:
        return [
            RigaFonte("openmeteo", _T - timedelta(hours=3), _T, "Quota esaurita (429)"),
            RigaFonte("dpc", _T, None, None),
            RigaFonte("sconosciuta", _T, None, None),
        ]

    async def _misurate() -> dict[str, Misurate]:
        return {"wildfire": Misurate(312_550, 312_550), "landslide": Misurate(0, 312_550)}

    async def _db() -> float:
        return 41.3

    async def _recenti(job_id: str, *, limit: int = 20) -> list[JobRun]:
        m = {"disco_dati_libero_gb": 120.0, "disco_dati_totale_gb": 500.0}
        return [JobRun(9, job_id, None, _T, _T, "ok", m, None, "w")]

    async def _passi(job_id: str) -> list[JobRun]:
        return [_run("skipped", {"reason": "BACKUP__BUCKET non impostato"})]

    async def _pausa() -> None:
        return None

    monkeypatch.setattr(ep.salute_repo, "fonti", _fonti)
    monkeypatch.setattr(ep.salute_repo, "misurate", _misurate)
    monkeypatch.setattr(ep.salute_repo, "dimensione_db_gb", _db)
    monkeypatch.setattr(ep.job_runs_repo, "recent", _recenti)
    monkeypatch.setattr(ep.job_runs_repo, "latest_per_scope", _passi)
    monkeypatch.setattr(ep, "pausa_glofas_fino", _pausa)

    class _Deps:
        settings = Settings()

    app = FastAPI()
    app.state.deps = _Deps()
    app.include_router(ep.router)
    r = TestClient(app).get("/api/installazione/salute")
    assert r.status_code == 200
    corpo = r.json()
    assert [f["id"] for f in corpo["fonti"]] == ["openmeteo", "dpc"]
    assert corpo["fonti"][0]["in_errore"] and not corpo["fonti"][1]["in_errore"]
    per_pericolo = {n["pericolo"]: n for n in corpo["non_misurate"]}
    assert per_pericolo["wildfire"]["cause"] == ["Open-Meteo pubblico"]
    assert per_pericolo["landslide"]["cause"] == []
    assert corpo["dischi"] == [
        {"nome": "Dati (LIMEN_DATA_ROOT)", "libero_gb": 120.0, "totale_gb": 500.0}
    ]
    assert corpo["backup"]["stato"] == "saltato"
    assert "usd" not in r.text.lower() and "$" not in r.text
