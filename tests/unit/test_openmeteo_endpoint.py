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
