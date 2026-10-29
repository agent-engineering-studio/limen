"""La raccolta degli eventi dalla stampa (#347): le parti senza rete né DB."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest

from limen.agents.chat_agents.estrattore_eventi import (
    EstrattoreEventi,
    EventoEstratto,
    _eventi,
    _testo,
)
from limen.api.jobs.raccolta_eventi import conferme, quando, raccogli, slug
from limen.config.settings import LLMSettings, Settings
from limen.core.models.hazard import HazardType
from limen.core.verifiche.esito import esito
from limen.data.repos.candidati_eventi_repo import aoi_della_regione, conta_testate
from limen.integrations.notizie.google_news import Titolo, leggi_rss

RSS = """<?xml version="1.0"?><rss><channel>
<item><title>Frana sulla SS106 a Melito - Gazzetta del Sud</title>
<link>https://news.google.com/a</link><pubDate>Fri, 10 Oct 2026 08:00:00 GMT</pubDate>
<source url="https://gazzettadelsud.it">Gazzetta del Sud</source></item>
<item><title>Senza testata</title><link>https://x</link>
<pubDate>Fri, 10 Oct 2026 08:00:00 GMT</pubDate></item>
</channel></rss>"""


def _evento(**kw: object) -> EventoEstratto:
    base: dict[str, object] = {
        "giorno": date(2026, 10, 28),
        "parte": "ignota",
        "luogo": "ex SS 303 a Lacedonia",
        "comuni": ["Lacedonia"],
        "regione": "Campania",
        "titoli": [0],
    }
    return EventoEstratto.model_validate(base | kw)


def test_il_titolo_perde_la_testata_in_coda_e_senza_testata_si_salta() -> None:
    titoli = leggi_rss(RSS)
    assert [(t.titolo, t.testata) for t in titoli] == [
        ("Frana sulla SS106 a Melito", "Gazzetta del Sud")
    ]
    assert titoli[0].pubblicato == datetime(2026, 10, 10, 8, tzinfo=UTC)


def test_due_titoli_dello_stesso_giornale_sono_una_testata() -> None:
    fonti = ({"testata": "Ulisse online"}, {"testata": "ulisse online "}, {"testata": "ANSA"})
    assert conta_testate(fonti) == 2


@pytest.mark.parametrize(
    ("regione", "aoi"),
    [
        ("Valle d'Aosta", "it-valle-d-aosta"),
        ("Trentino-Alto Adige", "it-trentino-alto-adige"),
        ("Emilia-Romagna", "it-emilia-romagna"),
        ("", None),
    ],
)
def test_la_regione_diventa_l_aoi(regione: str, aoi: str | None) -> None:
    assert aoi_della_regione(regione) == aoi


def test_slug_e_ora_come_la_skill() -> None:
    e = _evento(comuni=["Vietri sul Mare"], parte="sera")
    assert slug(HazardType.LANDSLIDE, e) == "2026-10-28-frana-vietri-sul-mare"
    t, precisione = quando(e)
    assert (t.hour, t.utcoffset().total_seconds(), precisione) == (20, 3600, "T2")
    assert quando(_evento())[1] == "T3"


def test_la_conferma_viene_da_un_altra_testata_sullo_stesso_comune_e_giorni() -> None:
    def t(testata: str, titolo: str, giorno: int) -> Titolo:
        return Titolo(
            titolo, testata, f"u-{testata}-{giorno}", datetime(2026, 10, giorno, 9, tzinfo=UTC)
        )

    titoli = [
        t("Orticalab", "Frana a Lacedonia", 28),
        t("Il Mattino", "Lacedonia, strada chiusa per frana", 29),
        t("Il Mattino", "Frana ad Ariano", 29),
        t("Irpinia News", "Lacedonia: la frana di un anno fa", 20),
    ]
    trovati = conferme(_evento(), titoli, {"orticalab"})
    assert [x.testata for x in trovati] == ["Il Mattino"]


def _misura(**kw: object) -> dict[str, object]:
    base: dict[str, object] = {
        "evento": "2026-10-10T10:00:00+00:00",
        "storico_dal": "2026-10-01T02:00:00+00:00",
        "celle": 40,
        "anticipo_ore_moderato": None,
        "anticipo_ore_alto": None,
        "classe_prevista_max": None,
        "fondo_classe_max": None,
        "corse": [],
        "adesso_classe_max": None,
        "adesso_primo_moderato": None,
        "adesso_non_misurato": 0,
    }
    return base | kw


def test_esito_come_il_paragrafo_5_della_skill() -> None:
    assert esito(_misura(storico_dal="2026-10-12T00:00:00+00:00"))[0] == "non_verificabile"
    assert esito(_misura(celle=0))[0] == "non_verificabile"
    previsto = _misura(anticipo_ore_moderato=40, classe_prevista_max="Moderate", corse=[{}])
    assert esito(previsto)[0] == "anticipata"
    # Melito: Moderato previsto 71 h prima, ma Moderato era anche il fondo.
    melito = previsto | {"anticipo_ore_moderato": 71, "fondo_classe_max": "Moderate"}
    assert esito(melito)[0] == "mancata"
    assert (
        esito(melito | {"classe_prevista_max": "High", "anticipo_ore_alto": 20})[0] == "anticipata"
    )
    assert esito(previsto | {"anticipo_ore_moderato": 3})[0] == "mancata"
    sweep = _misura(adesso_classe_max="High", adesso_primo_moderato="2026-10-10T06:00:00+00:00")
    assert esito(sweep)[0] == "contemporanea"


def _risposta(raw: str, stop: str = "end_turn") -> SimpleNamespace:
    msg = SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type="text", text=raw)])
    return SimpleNamespace(
        custom_id="landslide", result=SimpleNamespace(type="succeeded", message=msg)
    )


def test_un_titolo_inventato_non_e_una_fonte() -> None:
    raw = (
        '{"eventi": ['
        '{"giorno": "2026-10-28", "parte": "ignota", "luogo": "A", "comuni": ["A"],'
        ' "regione": "Lazio", "titoli": [0, 7]},'
        '{"giorno": "2026-10-28", "parte": "ignota", "luogo": "B", "comuni": ["B"],'
        ' "regione": "Lazio", "titoli": [9]}]}'
    )
    eventi = _eventi(_testo(_risposta(raw)), n_titoli=3)  # type: ignore[arg-type]
    assert eventi is not None
    assert [(e.luogo, e.titoli) for e in eventi] == [("A", [0])]
    assert _testo(_risposta(raw, stop="max_tokens")) is None  # type: ignore[arg-type]


async def test_senza_modello_o_chiave_la_raccolta_non_parte() -> None:
    # `_env_file=None`: il .env di una macchina con LLM__MODELS__EVENTI
    # dichiarato farebbe partire una raccolta vera dal test.
    def impostazioni(**llm: object) -> Settings:
        return cast(Any, Settings)(_env_file=None, llm=LLMSettings(**llm), anthropic_api_key=None)

    assert (await raccogli(impostazioni()))["status"] == "skipped"
    senza_chiave = await raccogli(impostazioni(models={"eventi": "claude-sonnet-5-5"}))
    assert senza_chiave["reason"] == "ANTHROPIC_API_KEY assente"


async def test_la_conferma_tiene_solo_i_titoli_esistenti_e_senza_risposta_nessuno(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    estrattore = object.__new__(EstrattoreEventi)
    estrattore._model = "m"  # type: ignore[attr-defined]

    async def esegui(richieste: dict[str, object]) -> dict[str, str]:
        return {"c0": '{"titoli": [1, 5]}'}

    monkeypatch.setattr(estrattore, "_esegui", esegui)
    t = Titolo("x", "y", "u", datetime(2026, 10, 28, tzinfo=UTC))
    casi = [(HazardType.LANDSLIDE, _evento(), [t, t]), (HazardType.LANDSLIDE, _evento(), [t])]
    assert await estrattore.conferma(casi) == [[1], []]


def test_un_buco_del_dato_non_cancella_le_ore_misurate() -> None:
    buco = _misura(adesso_non_misurato=3)
    assert esito(buco)[0] == "non_verificabile"
    salita = buco | {
        "adesso_misurato": 20,
        "adesso_classe_max": "High",
        "adesso_primo_moderato": "2026-10-10T06:00:00+00:00",
    }
    assert esito(salita)[0] == "contemporanea"


async def test_un_fact_check_a_mano_non_si_sovrascrive(monkeypatch: pytest.MonkeyPatch) -> None:
    from limen.api.jobs import raccolta_eventi as job
    from limen.data.repos.candidati_eventi_repo import Salvato

    segnati: list[dict[str, object]] = []

    async def fondi(c: object) -> Salvato:
        return Salvato(id=7, fonti=({"testata": "A"}, {"testata": "B"}), testate=2, slug=None)

    async def risolvi(nomi: object, regione: object) -> list[str]:
        return ["064041"]

    async def esiste(slug: str) -> bool:
        return True

    async def segna(id_: int, **kw: object) -> None:
        segnati.append(kw)

    async def vietato(*a: object, **kw: object) -> None:
        raise AssertionError("la riga a mano non va riscritta né rimisurata")

    monkeypatch.setattr(job.candidati_eventi_repo, "fondi", fondi)
    monkeypatch.setattr(job.candidati_eventi_repo, "risolvi_comuni", risolvi)
    monkeypatch.setattr(job.candidati_eventi_repo, "segna", segna)
    monkeypatch.setattr(job.verifiche_eventi_repo, "esiste", esiste)
    monkeypatch.setattr(job.verifiche_eventi_repo, "upsert", vietato)
    monkeypatch.setattr(job.anticipo_repo, "misura", vietato)
    esiti: Counter[str] = Counter()
    await job._registra(HazardType.LANDSLIDE, _evento(), [], esiti)
    assert esiti == Counter({"gia_verificato": 1})
    assert segnati == [
        {"stato": "verificato", "comuni": ["064041"], "slug": "2026-10-28-frana-lacedonia"}
    ]
