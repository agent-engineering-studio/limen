"""La raccolta degli eventi dalla stampa (#347): le parti senza rete né DB."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime, timedelta
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
    giorno = date(2026, 10, 28)
    assert (
        slug(HazardType.LANDSLIDE, giorno, "Vietri sul Mare") == "2026-10-28-frana-vietri-sul-mare"
    )
    # Un comune con omonimi porta il codice ISTAT: Castro (BG) e Castro (LE)
    # lo stesso giorno sono due verifiche, non una.
    assert (
        slug(HazardType.LANDSLIDE, giorno, "Castro", "075017") == "2026-10-28-frana-castro-075017"
    )
    t, precisione = quando(giorno, "sera")
    assert (t.hour, t.utcoffset().total_seconds(), precisione) == (20, 3600, "T2")
    assert quando(giorno, "ignota")[1] == "T3"


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
        "storico_dal": "2026-09-25T02:00:00+00:00",
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
    # La partizione più vecchia rimasta è dopo l'inizio del fondo (10 giorni
    # prima): la retention l'ha in parte cancellato, e un fondo a metà gonfia
    # gli anticipi.
    assert esito(_misura(partizioni_dal="2026-10-03")) == (
        "non_verificabile",
        "il fondo dei giorni prima non è più nello storico",
    )
    # Le previsioni `+24h` partono da poco (si scrivono solo da Moderato), ma
    # le partizioni coprono il fondo: si classifica.
    assert (
        esito(_misura(storico_dal="2026-10-08T00:00:00+00:00", partizioni_dal="2026-09-20"))[0]
        == "mancata"
    )
    assert esito(_misura(celle=0))[0] == "non_verificabile"
    # Job fermi nei giorni prima: non valutato, non mancato.
    assert esito(_misura(pericolo_valutato=False))[0] == "non_verificabile"
    assert esito(_misura(pericolo_valutato=True))[0] == "mancata"

    def corsa(ore_prima: int, classe: str) -> dict[str, str]:
        evento = datetime(2026, 10, 10, 10, tzinfo=UTC)
        return {"run_at": (evento - timedelta(hours=ore_prima)).isoformat(), "classe": classe}

    previsto = _misura(classe_prevista_max="Moderate", corse=[corsa(40, "Moderate")])
    assert esito(previsto)[0] == "anticipata"
    # Melito: Moderato previsto 71 h prima, ma Moderato era anche il fondo.
    melito = _misura(fondo_classe_max="Moderate", corse=[corsa(71, "Moderate")])
    assert esito(melito)[0] == "mancata"
    alto = melito | {"corse": [corsa(71, "Moderate"), corsa(20, "High")]}
    assert esito(alto) == ("anticipata", "High previsto 20 h prima, sopra un fondo Moderate")
    assert esito(_misura(corse=[corsa(3, "Moderate")]))[0] == "mancata"
    # Fondo Alto: l'Alto di 72 h prima è il fondo; il Molto alto arriva 2 h prima.
    tardi = _misura(fondo_classe_max="High", corse=[corsa(72, "High"), corsa(2, "VeryHigh")])
    assert esito(tardi)[0] == "mancata"
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
        return Salvato(
            id=7,
            fonti=({"testata": "A"}, {"testata": "B"}),
            testate=2,
            slug=None,
            stato="una_testata",
            giorno=date(2026, 10, 28),
            parte="ignota",
            luogo="Lacedonia",
            regione="Campania",
            nomi_comuni=("Lacedonia",),
        )

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

    async def senza_omonimi(*a: object) -> bool:
        return False

    monkeypatch.setattr(job.candidati_eventi_repo, "ha_omonimi", senza_omonimi)
    monkeypatch.setattr(job.candidati_eventi_repo, "slug_di_un_altro", senza_omonimi)
    monkeypatch.setattr(job.verifiche_eventi_repo, "esiste", esiste)
    monkeypatch.setattr(job.verifiche_eventi_repo, "upsert", vietato)
    monkeypatch.setattr(job.anticipo_repo, "misura", vietato)
    esiti: Counter[str] = Counter()
    await job._registra(HazardType.LANDSLIDE, _evento(), [], esiti)
    assert esiti == Counter({"gia_verificato": 1})
    assert segnati == [
        {"stato": "verificato", "comuni": ["064041"], "slug": "2026-10-28-frana-lacedonia"}
    ]


async def test_oltre_il_budget_del_mese_la_raccolta_non_parte(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from decimal import Decimal

    from limen.api.jobs import raccolta_eventi as job

    async def spesa() -> Decimal:
        return Decimal("10.5")

    async def vietato(**kw: object) -> object:
        raise AssertionError("oltre il budget non si cerca né si chiama Claude")

    monkeypatch.setattr(job.budget, "spesa_del_mese", spesa)
    monkeypatch.setattr(job, "titoli_per_pericolo", vietato)
    impostazioni = cast(Any, Settings)(
        _env_file=None,
        llm=LLMSettings(models={"eventi": "claude-sonnet-5-5"}, anthropic_budget_mensile_usd=10),
        anthropic_api_key="sk-prova",
    )
    monkeypatch.setattr(job.budget, "get_settings", lambda: impostazioni)
    out = await raccogli(impostazioni)
    assert "tetto mensile" in out["reason"]


async def test_un_evento_gia_verificato_non_si_rimisura(monkeypatch: pytest.MonkeyPatch) -> None:
    from limen.api.jobs import raccolta_eventi as job
    from limen.data.repos.candidati_eventi_repo import Salvato

    async def fondi(c: object) -> Salvato:
        return Salvato(
            id=7,
            fonti=({"testata": "A"}, {"testata": "B"}),
            testate=2,
            slug="2026-10-28-frana-lacedonia",
            stato="verificato",
            giorno=date(2026, 10, 28),
            parte="ignota",
            luogo="Lacedonia",
            regione="Campania",
            nomi_comuni=("Lacedonia",),
        )

    async def risolvi(nomi: object, regione: object) -> list[str]:
        return ["064041"]

    async def vietato(*a: object, **kw: object) -> None:
        raise AssertionError("la misura congelata non si rifà")

    monkeypatch.setattr(job.candidati_eventi_repo, "fondi", fondi)
    monkeypatch.setattr(job.candidati_eventi_repo, "risolvi_comuni", risolvi)
    monkeypatch.setattr(job.anticipo_repo, "misura", vietato)
    monkeypatch.setattr(job.verifiche_eventi_repo, "upsert", vietato)
    esiti: Counter[str] = Counter()
    await job._registra(HazardType.LANDSLIDE, _evento(), [], esiti)
    assert esiti == Counter({"gia_verificato": 1})


async def test_un_secondo_incidente_lo_stesso_giorno_ha_il_suo_slug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from limen.api.jobs import raccolta_eventi as job
    from limen.data.repos.candidati_eventi_repo import Salvato

    scritte: list[str] = []

    async def fondi(c: object) -> Salvato:
        return Salvato(
            id=8,
            fonti=({"testata": "A"}, {"testata": "B"}),
            testate=2,
            slug=None,
            stato="una_testata",
            giorno=date(2026, 10, 28),
            parte="ignota",
            luogo="via Roma a Lacedonia",
            regione="Campania",
            nomi_comuni=("Lacedonia",),
        )

    async def risolvi(nomi: object, regione: object) -> list[str]:
        return ["064041"]

    async def no(*a: object) -> bool:
        return False

    async def esiste(slug: str) -> bool:
        return slug == "2026-10-28-frana-lacedonia"

    async def di_un_altro(slug: str, id_: int) -> bool:
        return slug == "2026-10-28-frana-lacedonia"

    async def misura(**kw: object) -> dict[str, object]:
        return _misura()

    async def upsert(v: object) -> None:
        scritte.append(v.slug)  # type: ignore[attr-defined]

    async def niente(*a: object, **kw: object) -> None:
        return None

    monkeypatch.setattr(job.candidati_eventi_repo, "fondi", fondi)
    monkeypatch.setattr(job.candidati_eventi_repo, "risolvi_comuni", risolvi)
    monkeypatch.setattr(job.candidati_eventi_repo, "ha_omonimi", no)
    monkeypatch.setattr(job.candidati_eventi_repo, "slug_di_un_altro", di_un_altro)
    monkeypatch.setattr(job.candidati_eventi_repo, "segna", niente)
    monkeypatch.setattr(job.candidati_eventi_repo, "prenota", niente)
    monkeypatch.setattr(job.verifiche_eventi_repo, "esiste", esiste)
    monkeypatch.setattr(job.verifiche_eventi_repo, "upsert", upsert)
    monkeypatch.setattr(job.anticipo_repo, "misura", misura)
    esiti: Counter[str] = Counter()
    await job._registra(HazardType.LANDSLIDE, _evento(), [], esiti)
    assert scritte == ["2026-10-28-frana-lacedonia-2"]

    # Prenotato da un altro candidato ma non ancora scritto: occupato lo stesso.
    async def nessuna(slug: str) -> bool:
        return False

    monkeypatch.setattr(job.verifiche_eventi_repo, "esiste", nessuna)
    scritte.clear()
    await job._registra(HazardType.LANDSLIDE, _evento(), [], esiti)
    assert scritte == ["2026-10-28-frana-lacedonia-2"]


def test_l_elenco_data_i_titoli_in_ora_italiana() -> None:
    from datetime import UTC, datetime

    from limen.agents.chat_agents.estrattore_eventi import elenco
    from limen.integrations.notizie.google_news import Titolo

    t = Titolo(
        "Frana a Lacedonia", "Ottopagine", "https://x/1", datetime(2026, 10, 27, 23, 30, tzinfo=UTC)
    )
    assert "2026-10-28" in elenco([t])


async def test_se_l_estrazione_finisce_il_tetto_la_conferma_non_parte(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import replace
    from decimal import Decimal

    from limen.agents.chat_agents.estrattore_eventi import Consumo
    from limen.api.jobs import raccolta_eventi as job

    titolo = Titolo(
        "Frana a Lacedonia", "Ottopagine", "https://x/1", datetime(2026, 10, 28, tzinfo=UTC)
    )
    spesa = {"usd": Decimal("9")}
    registrati: list[str] = []
    richieste_di_conferma: list[int] = []

    async def spesa_del_mese() -> Decimal:
        return spesa["usd"]

    async def registra(**kw: Any) -> Decimal:
        registrati.append(kw["riferimento"])
        spesa["usd"] += Decimal("2")
        return Decimal("2")

    async def titoli_per_pericolo(**kw: object) -> dict[HazardType, list[Titolo]]:
        return {HazardType.LANDSLIDE: [titolo]}

    async def estrai(self: Any, titoli: object) -> dict[HazardType, list[EventoEstratto]]:
        self.consumi.append(Consumo("estrazione", 1000, 100))
        return {HazardType.LANDSLIDE: [_evento()]}

    async def conferma(self: Any, casi: list[object]) -> list[list[int]]:
        richieste_di_conferma.append(len(casi))
        return [[] for _ in casi]

    async def cerca_conferme(*a: object) -> list[Titolo]:
        return [replace(titolo, testata="Il Mattino", url="https://x/2")]

    async def registra_evento(*a: object) -> None:
        return None

    impostazioni = cast(Any, Settings)(
        _env_file=None,
        llm=LLMSettings(models={"eventi": "claude-sonnet-5-5"}, anthropic_budget_mensile_usd=10),
        anthropic_api_key="sk-prova",
    )
    monkeypatch.setattr(job.budget, "get_settings", lambda: impostazioni)
    monkeypatch.setattr(job.budget, "spesa_del_mese", spesa_del_mese)
    monkeypatch.setattr(job.budget, "registra", registra)
    monkeypatch.setattr(job, "titoli_per_pericolo", titoli_per_pericolo)
    monkeypatch.setattr(job, "cerca_conferme", cerca_conferme)
    monkeypatch.setattr(job, "_registra", registra_evento)
    monkeypatch.setattr(EstrattoreEventi, "estrai", estrai)
    monkeypatch.setattr(EstrattoreEventi, "conferma", conferma)

    await raccogli(impostazioni)
    # L'estrazione è registrata prima di decidere, e la conferma parte vuota.
    assert registrati == ["estrazione"]
    assert richieste_di_conferma == [0]


def test_l_anticipo_minimo_si_confronta_prima_di_arrotondare() -> None:
    evento = datetime(2026, 10, 10, 10, tzinfo=UTC)
    # 5 h 40': arrotondate sarebbero 6, il minimo.
    corsa = {"run_at": (evento - timedelta(hours=5, minutes=40)).isoformat(), "classe": "High"}
    assert esito(_misura(classe_prevista_max="High", corse=[corsa]))[0] != "anticipata"


async def test_un_batch_scaduto_e_annullato_conta_i_token_delle_richieste_riuscite() -> None:
    from pydantic import SecretStr

    from tests.unit.test_fedelta_racconti import _Batches, _risposta

    # Il batch resta in corso oltre l'attesa: si annulla, si aspetta la
    # chiusura, e la richiesta già riuscita resta pagata e letta.
    batches = _Batches([_risposta("c0", '{"titoli": [1]}')], giri=1)
    e = EstrattoreEventi(
        api_key=SecretStr("sk-test"),
        model="claude-sonnet-5-5",
        attesa_massima_s=0.0,
        intervallo_s=0.0,
    )
    e._client = cast(Any, SimpleNamespace(messages=SimpleNamespace(batches=batches)))
    testi = await e._esegui({"c0": cast(Any, {})})
    assert batches.annullato
    assert testi == {"c0": '{"titoli": [1]}'}
    assert [(c.batch_id, c.input_tokens) for c in e.consumi] == [("b1", 1500)]


def test_le_regioni_ammesse_sono_le_aoi_regionali() -> None:
    import json
    from importlib import resources

    from limen.agents.chat_agents.estrattore_eventi import REGIONI

    seme = json.loads(
        resources.files("limen.data.seed").joinpath("italy_regions_aoi.geojson").read_text()
    )
    aoi = {f["properties"]["id"] for f in seme["features"]}
    assert {aoi_della_regione(r) for r in REGIONI} == aoi


async def test_una_registrazione_interrotta_si_riprende_con_lo_stesso_slug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from limen.api.jobs import raccolta_eventi as job
    from limen.data.repos.candidati_eventi_repo import Salvato

    # Il giro prima ha prenotato lo slug e scritto la verifica, poi è caduto
    # prima della frana: la verifica esiste, ma è nostra, non un fact check.
    scritte: list[str] = []
    frane: list[object] = []
    segnati: list[dict[str, object]] = []

    async def fondi(c: object) -> Salvato:
        return Salvato(
            id=9,
            fonti=({"testata": "A"}, {"testata": "B"}),
            testate=2,
            slug="2026-10-28-frana-lacedonia",
            stato="una_testata",
            giorno=date(2026, 10, 28),
            parte="ignota",
            luogo="Lacedonia",
            regione="Campania",
            nomi_comuni=("Lacedonia",),
        )

    async def risolvi(nomi: object, regione: object) -> list[str]:
        return ["064041"]

    async def vietato(*a: object, **kw: object) -> None:
        raise AssertionError("lo slug prenotato non si ricerca")

    async def misura(**kw: object) -> dict[str, object]:
        return _misura()

    async def upsert(v: Any) -> tuple[object, str]:
        scritte.append(v.slug)
        return (object(), "P10")

    async def landslide(righe: list[object]) -> None:
        frane.extend(righe)

    async def segna(id_: int, **kw: object) -> None:
        segnati.append(kw)

    monkeypatch.setattr(job.candidati_eventi_repo, "fondi", fondi)
    monkeypatch.setattr(job.candidati_eventi_repo, "risolvi_comuni", risolvi)
    monkeypatch.setattr(job.candidati_eventi_repo, "segna", segna)
    monkeypatch.setattr(job.candidati_eventi_repo, "prenota", vietato)
    monkeypatch.setattr(job.verifiche_eventi_repo, "esiste", vietato)
    monkeypatch.setattr(job.verifiche_eventi_repo, "upsert", upsert)
    monkeypatch.setattr(job.anticipo_repo, "misura", misura)
    monkeypatch.setattr(job, "landslide_upsert", landslide)
    monkeypatch.setattr(job, "frana_da_verifica", lambda v, *a: v.slug)
    esiti: Counter[str] = Counter()
    await job._registra(HazardType.LANDSLIDE, _evento(), [], esiti)
    assert scritte == ["2026-10-28-frana-lacedonia"]
    assert frane == ["2026-10-28-frana-lacedonia"]
    assert segnati[-1]["stato"] == "verificato"
