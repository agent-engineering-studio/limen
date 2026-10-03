"""Dove va a finire la richiesta meteo (#142).

L'API pubblica ha un tetto di 10.000 chiamate al giorno e lo sweep ne chiede
circa diecimila località a tick: esaurirlo ha spento alluvione e incendio su
tutta l'Italia. Open-Meteo è open source e si ospita, e questi test fissano
le tre regole della sostituzione: vuota non cambia niente, valorizzata vale
per le previsioni, e portata e onde restano dove sono perché GloFAS non è
auto-ospitabile.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from limen.config.settings import get_settings
from limen.integrations.openmeteo import client as meteo_client
from limen.integrations.openmeteo import flood as meteo_flood


@pytest.fixture(autouse=True)
def _settings_pulite() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_senza_configurazione_si_parla_con_l_api_pubblica(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Esplicito a vuoto, non «non impostato»: `Settings` legge anche il `.env`
    # del repo, e su una macchina che ospita davvero l'istanza quel file le
    # variabili ce le ha. Un test che passa o fallisce secondo la macchina non
    # sta misurando il codice.
    for chiave in ("OPENMETEO__FORECAST_URL", "OPENMETEO__ARCHIVE_URL", "OPENMETEO__MODELS"):
        monkeypatch.setenv(chiave, "")
    get_settings.cache_clear()

    assert meteo_client.forecast_url() == meteo_client.FORECAST_URL
    assert meteo_client.archive_url() == meteo_client.ARCHIVE_URL
    assert meteo_client.weather_model() is None


def test_l_istanza_propria_sostituisce_previsione_e_archivio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENMETEO__FORECAST_URL", "http://openmeteo:8080/v1/forecast")
    monkeypatch.setenv("OPENMETEO__ARCHIVE_URL", "http://openmeteo:8080/v1/archive")
    monkeypatch.setenv("OPENMETEO__MODELS", "ecmwf_ifs025")
    get_settings.cache_clear()

    assert meteo_client.forecast_url() == "http://openmeteo:8080/v1/forecast"
    assert meteo_client.archive_url() == "http://openmeteo:8080/v1/archive"
    assert meteo_client.weather_model() == "ecmwf_ifs025"


def test_la_griglia_pluviale_segue_la_previsione(monkeypatch: pytest.MonkeyPatch) -> None:
    """È il consumo più grosso che resta, e passa dallo stesso endpoint."""
    monkeypatch.setenv("OPENMETEO__FORECAST_URL", "http://openmeteo:8080/v1/forecast")
    get_settings.cache_clear()

    from limen.integrations.openmeteo.client import forecast_url

    assert forecast_url() == "http://openmeteo:8080/v1/forecast"
    # GloFAS non è pubblicato sul bucket AWS di Open-Meteo, quindi il ramo
    # fluviale non si può auto-ospitare e non deve seguire la previsione.
    assert meteo_flood.FLOOD_URL.startswith("https://flood-api.open-meteo.com")
    assert meteo_flood.MARINE_URL.startswith("https://marine-api.open-meteo.com")


def test_il_modello_si_nomina_solo_sulle_previsioni(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENMETEO__MODELS", "ecmwf_ifs025")
    get_settings.cache_clear()

    originali = {"hourly": "precipitation"}
    params = meteo_flood._with_model(originali)
    assert params["models"] == "ecmwf_ifs025"
    # Non muta l'originale: la stessa forma serve anche alle chiamate su
    # GloFAS, che un `models` del modello meteo lo rifiuterebbero.
    assert originali == {"hourly": "precipitation"}


def test_senza_modello_i_parametri_restano_quelli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENMETEO__MODELS", "")
    get_settings.cache_clear()

    originali = {"hourly": "precipitation"}
    assert meteo_flood._with_model(originali) == originali


def _ore(adesso: datetime, valori: list[float]) -> dict[str, object]:
    """Una risposta oraria che parte due ore prima di `adesso`."""
    inizio = adesso.replace(minute=0, second=0, microsecond=0) - timedelta(hours=2)
    return {
        "hourly": {
            "time": [
                (inizio + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(len(valori))
            ],
            "precipitation": valori,
        }
    }


async def test_la_pioggia_del_riquadro_passa_dall_istanza_propria(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#159: il riquadro della cella chiedeva all'API pubblica dal browser."""
    monkeypatch.setenv("OPENMETEO__FORECAST_URL", "http://openmeteo:8080/v1/forecast")
    get_settings.cache_clear()
    adesso = datetime.now(UTC)
    # Due ore passate (fuori dalla finestra), poi 48 ore di pioggia, poi altre
    # ore oltre le 48 che non vanno contate.
    valori = [9.0, 9.0] + [1.0] * 47 + [4.0] + [9.0] * 20
    chieste: list[str] = []

    def risponde(req: httpx.Request) -> httpx.Response:
        chieste.append(str(req.url))
        return httpx.Response(200, json=_ore(adesso, valori))

    async with httpx.AsyncClient(transport=httpx.MockTransport(risponde)) as http:
        esito = await meteo_client.OpenMeteoHttpClient(http_client=http).get_rain_outlook(
            lon=13.9, lat=42.3
        )

    assert chieste and chieste[0].startswith("http://openmeteo:8080/v1/forecast")
    assert esito is not None
    assert esito["peak_mmh"] == 4.0
    # Le ore già passate e quelle oltre le 48 restano fuori: 47 ore a 1 mm e una a 4.
    assert esito["total_mm"] == 51.0


async def test_senza_dati_il_riquadro_dice_non_lo_so(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nessun campione non è «niente pioggia»: è `None`."""
    monkeypatch.setenv("OPENMETEO__FORECAST_URL", "http://openmeteo:8080/v1/forecast")
    get_settings.cache_clear()

    def vuota(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"hourly": {"time": [], "precipitation": []}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(vuota)) as http:
        esito = await meteo_client.OpenMeteoHttpClient(http_client=http).get_rain_outlook(
            lon=13.9, lat=42.3
        )
    assert esito is None
