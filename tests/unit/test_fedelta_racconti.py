"""Il revisore di fedeltà: i due controlli e quando il job non deve girare."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest

from limen.agents.chat_agents.briefing_eval import allowed_numbers_from_text
from limen.agents.chat_agents.fedelta import RevisoreFedelta, controllo_numeri
from limen.agents.llm_factory.stub import StubLlmClientFactory
from limen.api.jobs import fedelta_racconti as fr
from limen.config.settings import LLMSettings, Settings
from limen.core.models.hazard import HazardType
from limen.data.repos.spiegazioni_repo import DaGiudicare

INGRESSO = (
    "Aoi: it-basilicata\nPericolo: landslide\nCelle: 23214; high+: 41; "
    "distribuzione: {'Low': 20000, 'Moderate': 3173, 'High': 41}\n"
    "Top cells:\n- it-basilicata|1|2 score=0.734 level=High driver=[s=0.95, m=0.41]"
)


def _parole(n: int) -> str:
    return " ".join(["parola"] * n)


def test_i_numeri_dell_ingresso_sono_ammessi_anche_all_italiana() -> None:
    ammessi = allowed_numbers_from_text(INGRESSO)
    assert {"41", "0,73", "0.73"} <= ammessi
    testo = f"Su 23.214 aree, 41 sono in classe alta. {_parole(160)}"
    assert controllo_numeri(testo, INGRESSO).unknown_numbers == []


def test_un_numero_inventato_si_vede() -> None:
    testo = f"Su 23.214 aree, 57 sono in classe alta. {_parole(160)}"
    assert controllo_numeri(testo, INGRESSO).unknown_numbers == ["57"]


def test_le_citazioni_non_contano() -> None:
    testo = (
        f"Su 23.214 aree, 41 in classe alta. {_parole(160)}\n\n**Fonti**\n- Guzzetti 2008, p. 98"
    )
    assert controllo_numeri(testo, INGRESSO).unknown_numbers == []


class _Client:
    def __init__(self, risposta: str | Exception) -> None:
        self.risposta = risposta
        self.model = "glm52"

    async def chat(self, _messages: Any, **_kw: Any) -> str:
        if isinstance(self.risposta, Exception):
            raise self.risposta
        return self.risposta


async def test_il_revisore_legge_il_suo_json() -> None:
    g = await RevisoreFedelta(_Client('{"fedele": false, "problemi": ["la pioggia"]}')).giudica(
        "t", INGRESSO
    )
    assert g is not None and g.fedele is False and g.problemi == ["la pioggia"]


@pytest.mark.parametrize("risposta", ["non è json", TimeoutError("colibrì")])
async def test_un_revisore_che_non_risponde_non_assolve(risposta: Any) -> None:
    assert await RevisoreFedelta(_Client(risposta)).giudica("t", INGRESSO) is None


def test_il_verdetto() -> None:
    assert fr.verdetto(numeri_sconosciuti=["57"], giudizio={"fedele": True}) is False
    assert fr.verdetto(numeri_sconosciuti=[], giudizio=None) is None
    assert fr.verdetto(numeri_sconosciuti=[], giudizio={"fedele": True}) is True
    assert fr.verdetto(numeri_sconosciuti=[], giudizio={"fedele": False}) is False


def _settings(**llm: Any) -> Settings:
    return cast(Settings, cast(Any, Settings)(_env_file=None, llm=LLMSettings(**llm)))


async def test_senza_ruolo_dichiarato_non_gira() -> None:
    out = await fr.controlla_fedelta(_settings(), StubLlmClientFactory())
    assert out["status"] == "skipped"


async def test_una_variabile_vuota_non_accende_il_revisore() -> None:
    out = await fr.controlla_fedelta(_settings(models={"fedelta": ""}), StubLlmClientFactory())
    assert out["status"] == "skipped"


async def test_il_modello_lento_aspetta_la_sera() -> None:
    # Una finestra che comincia fra un'ora: adesso è fuori, qualunque ora sia.
    ora = datetime.now(UTC).hour
    settings = _settings(
        models={"fedelta": "glm52"}, slow_models_window_utc=((ora + 1) % 24, (ora + 2) % 24)
    )
    out = await fr.controlla_fedelta(settings, StubLlmClientFactory())
    assert out == {"status": "skipped", "reason": "modello lento fuori finestra", "model": "glm52"}


async def test_il_verdetto_va_accanto_alla_spiegazione(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(models={"fedelta": "fast"})
    candidata = DaGiudicare(
        aoi_id="it-basilicata",
        hazard=HazardType.LANDSLIDE,
        scritta=datetime(2026, 10, 11, 8, tzinfo=UTC),
        modello="fast-cloud",
        testo=f"Su 23.214 aree, 57 sono in classe alta. {_parole(160)}",
        ingresso=INGRESSO,
    )
    scritti: list[dict[str, Any]] = []

    async def _da_giudicare(**_kw: Any) -> list[DaGiudicare]:
        return [candidata]

    async def _scrivi(**kw: Any) -> bool:
        scritti.append(kw)
        return True

    class _Factory:
        provider = "test"

        def create(self, _role: str) -> _Client:
            return _Client('{"fedele": true, "problemi": []}')

    class _Tracked:
        async def __aenter__(self) -> dict[str, Any]:
            return {}

        async def __aexit__(self, *_a: Any) -> None:
            return None

    monkeypatch.setattr(fr.spiegazioni_repo, "da_giudicare", _da_giudicare)
    monkeypatch.setattr(fr.spiegazioni_repo, "scrivi_fedelta", _scrivi)
    monkeypatch.setattr(fr, "tracked", lambda *_a, **_k: _Tracked())

    out = await fr.controlla_fedelta(settings, _Factory())
    assert out == {"giudicate": 1, "fedeli": 0, "infedeli": 1, "senza_giudizio": 0}
    # Il revisore ha assolto, ma il 57 non c'è nei dati: vince il controllo dei numeri.
    assert scritti[0]["fedelta"]["fedele"] is False
    assert scritti[0]["fedelta"]["numeri_sconosciuti"] == ["57"]
    assert scritti[0]["fedelta"]["autore"] == "fast-cloud"


def test_fedelta_e_un_ruolo_asincrono() -> None:
    LLMSettings(models={"fedelta": "glm52"})
    with pytest.raises(ValueError, match="RISK_ANALYST"):
        LLMSettings(models={"risk_analyst": "glm52"})


async def test_un_giudizio_su_un_testo_riscritto_non_conta(
    monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    """Il briefing ha riscritto la spiegazione durante la revisione: il
    verdetto non si salva, quindi niente allarme e niente conteggio (#206)."""
    settings = _settings(models={"fedelta": "fast"})
    candidata = DaGiudicare(
        aoi_id="it-basilicata",
        hazard=HazardType.LANDSLIDE,
        scritta=datetime(2026, 10, 11, 8, tzinfo=UTC),
        modello="fast-cloud",
        testo=f"Su 23.214 aree, 57 sono in classe alta. {_parole(160)}",
        ingresso=INGRESSO,
    )

    async def _da_giudicare(**_kw: Any) -> list[DaGiudicare]:
        return [candidata]

    async def _scrivi(**_kw: Any) -> bool:
        return False

    class _Factory:
        provider = "test"

        def create(self, _role: str) -> _Client:
            return _Client('{"fedele": true, "problemi": []}')

    class _Tracked:
        async def __aenter__(self) -> dict[str, Any]:
            return {}

        async def __aexit__(self, *_a: Any) -> None:
            return None

    monkeypatch.setattr(fr.spiegazioni_repo, "da_giudicare", _da_giudicare)
    monkeypatch.setattr(fr.spiegazioni_repo, "scrivi_fedelta", _scrivi)
    monkeypatch.setattr(fr, "tracked", lambda *_a, **_k: _Tracked())

    out = await fr.controlla_fedelta(settings, _Factory())
    assert out == {"giudicate": 0, "fedeli": 0, "infedeli": 0, "senza_giudizio": 0}
    assert "racconto.infedele" not in capsys.readouterr().out
