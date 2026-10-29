"""Il revisore di fedeltà: i due controlli e quando il job non deve girare."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest
from pydantic import SecretStr

from limen.agents.chat_agents.briefing_eval import allowed_numbers_from_text
from limen.agents.chat_agents.fedelta import Giudizio, RevisoreFedelta, controllo_numeri
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


def _risposta(custom_id: str, testo: str | None, *, stop: str = "end_turn") -> Any:
    content = [SimpleNamespace(type="thinking", thinking="")]
    if testo is not None:
        content.append(SimpleNamespace(type="text", text=testo))
    message = SimpleNamespace(content=content, stop_reason=stop)
    return SimpleNamespace(
        custom_id=custom_id, result=SimpleNamespace(type="succeeded", message=message)
    )


class _Batches:
    """Il pezzo di `client.messages.batches` che il revisore usa."""

    def __init__(self, risultati: list[Any], *, giri: int = 0, errore: Exception | None = None):
        self.risultati = risultati
        self.giri = giri
        self.errore = errore
        self.richieste: list[Any] = []
        self.annullato = False

    def _batch(self) -> SimpleNamespace:
        return SimpleNamespace(
            id="b1", processing_status="ended" if self.giri <= 0 else "in_progress"
        )

    async def create(self, *, requests: list[Any]) -> SimpleNamespace:
        if self.errore is not None:
            raise self.errore
        self.richieste = requests
        return self._batch()

    async def retrieve(self, _id: str) -> SimpleNamespace:
        self.giri -= 1
        return self._batch()

    async def cancel(self, _id: str) -> None:
        self.annullato = True

    async def results(self, _id: str) -> AsyncIterator[Any]:
        async def _gen() -> AsyncIterator[Any]:
            for r in self.risultati:
                yield r

        return _gen()


def _revisore(batches: _Batches, *, attesa_s: float = 60.0) -> RevisoreFedelta:
    r = RevisoreFedelta(
        api_key=SecretStr("sk-test"), model="claude-sonnet-5-5", attesa_massima_s=attesa_s
    )
    r._intervallo_s = 0.0
    r._client = cast(Any, SimpleNamespace(messages=SimpleNamespace(batches=batches)))
    return r


async def test_il_revisore_legge_il_suo_json_nell_ordine_giusto() -> None:
    # I risultati di un batch arrivano in qualunque ordine: contano i custom_id.
    batches = _Batches(
        [
            _risposta("s1", '{"fedele": true, "problemi": []}'),
            _risposta("s0", '{"fedele": false, "problemi": ["la pioggia"]}'),
        ],
        giri=2,
    )
    g = await _revisore(batches).giudica([("t0", INGRESSO), ("t1", INGRESSO)])
    assert g[0] is not None and g[0].fedele is False and g[0].problemi == ["la pioggia"]
    assert g[1] is not None and g[1].fedele is True
    params = batches.richieste[0]["params"]
    assert params["model"] == "claude-sonnet-5-5"
    assert params["output_config"]["format"]["type"] == "json_schema"
    assert "temperature" not in params


@pytest.mark.parametrize(
    "risultato",
    [
        _risposta("s0", "non è json"),
        _risposta("s0", '{"fedele": true, "problemi": ["1", "2", "3", "4", "5", "6"]}'),
        _risposta("s0", None, stop="refusal"),
        _risposta("s0", '{"fedele": tr', stop="max_tokens"),
        SimpleNamespace(custom_id="s0", result=SimpleNamespace(type="errored")),
    ],
)
async def test_un_revisore_che_non_risponde_non_assolve(risultato: Any) -> None:
    assert await _revisore(_Batches([risultato])).giudica([("t", INGRESSO)]) == [None]


async def test_un_batch_che_non_parte_non_assolve() -> None:
    import anthropic

    errore = anthropic.APIConnectionError(request=httpx.Request("POST", "https://x"))
    batches = _Batches([], errore=errore)
    assert await _revisore(batches).giudica([("a", INGRESSO), ("b", INGRESSO)]) == [None, None]


async def test_un_batch_che_non_finisce_si_annulla() -> None:
    batches = _Batches([_risposta("s0", '{"fedele": true, "problemi": []}')], giri=10**6)
    assert await _revisore(batches, attesa_s=0.0).giudica([("t", INGRESSO)]) == [None]
    assert batches.annullato


def test_il_verdetto() -> None:
    assert fr.verdetto(numeri_sconosciuti=["57"], giudizio={"fedele": True}) is False
    assert fr.verdetto(numeri_sconosciuti=[], giudizio=None) is None
    assert fr.verdetto(numeri_sconosciuti=[], giudizio={"fedele": True}) is True
    assert fr.verdetto(numeri_sconosciuti=[], giudizio={"fedele": False}) is False


def _settings(*, chiave: str | None = None, **llm: Any) -> Settings:
    return cast(
        Settings,
        cast(Any, Settings)(_env_file=None, llm=LLMSettings(**llm), anthropic_api_key=chiave),
    )


async def test_senza_ruolo_dichiarato_non_gira() -> None:
    out = await fr.controlla_fedelta(_settings())
    assert out["status"] == "skipped"


async def test_una_variabile_vuota_non_accende_il_revisore() -> None:
    out = await fr.controlla_fedelta(_settings(models={"fedelta": ""}))
    assert out["status"] == "skipped"


async def test_senza_chiave_anthropic_non_gira() -> None:
    out = await fr.controlla_fedelta(_settings(models={"fedelta": "claude-sonnet-5-5"}))
    assert out["status"] == "skipped" and out["reason"] == "ANTHROPIC_API_KEY assente"


def _revisore_fisso(risposta: str) -> type:
    class _Revisore:
        def __init__(self, **_kw: Any) -> None:
            pass

        async def giudica(self, coppie: list[tuple[str, str]]) -> list[Giudizio | None]:
            return [Giudizio.model_validate_json(risposta) for _ in coppie]

    return _Revisore


async def test_il_verdetto_va_accanto_alla_spiegazione(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(models={"fedelta": "claude-sonnet-5-5"}, chiave="sk-test")
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

    class _Tracked:
        async def __aenter__(self) -> dict[str, Any]:
            return {}

        async def __aexit__(self, *_a: Any) -> None:
            return None

    monkeypatch.setattr(fr.spiegazioni_repo, "da_giudicare", _da_giudicare)
    monkeypatch.setattr(fr.spiegazioni_repo, "scrivi_fedelta", _scrivi)
    monkeypatch.setattr(fr, "tracked", lambda *_a, **_k: _Tracked())
    monkeypatch.setattr(fr, "RevisoreFedelta", _revisore_fisso('{"fedele": true, "problemi": []}'))

    out = await fr.controlla_fedelta(settings)
    assert out == {"giudicate": 1, "fedeli": 0, "infedeli": 1, "senza_giudizio": 0}
    # Il revisore ha assolto, ma il 57 non c'è nei dati: vince il controllo dei numeri.
    assert scritti[0]["fedelta"]["fedele"] is False
    assert scritti[0]["fedelta"]["numeri_sconosciuti"] == ["57"]
    assert scritti[0]["fedelta"]["autore"] == "fast-cloud"


async def test_un_giudizio_su_un_testo_riscritto_non_conta(
    monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    """Il briefing ha riscritto la spiegazione durante la revisione: il
    verdetto non si salva, quindi niente allarme e niente conteggio (#206)."""
    settings = _settings(models={"fedelta": "claude-sonnet-5-5"}, chiave="sk-test")
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

    class _Tracked:
        async def __aenter__(self) -> dict[str, Any]:
            return {}

        async def __aexit__(self, *_a: Any) -> None:
            return None

    monkeypatch.setattr(fr.spiegazioni_repo, "da_giudicare", _da_giudicare)
    monkeypatch.setattr(fr.spiegazioni_repo, "scrivi_fedelta", _scrivi)
    monkeypatch.setattr(fr, "tracked", lambda *_a, **_k: _Tracked())
    monkeypatch.setattr(fr, "RevisoreFedelta", _revisore_fisso('{"fedele": true, "problemi": []}'))

    out = await fr.controlla_fedelta(settings)
    assert out == {"giudicate": 0, "fedeli": 0, "infedeli": 0, "senza_giudizio": 0}
    assert "racconto.infedele" not in capsys.readouterr().out
