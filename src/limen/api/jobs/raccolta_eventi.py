"""La raccolta quotidiana degli eventi dalla stampa (#347, epica #345).

Il truth set del traguardo — il 90 % degli eventi della cronaca previsti a
72 h — si riempiva solo quando qualcuno lanciava il fact check a mano, e
``risk_assessments`` dimentica tutto dopo 14 giorni: un evento non verificato
in tempo non è più misurabile. Ogni mattina, a ``LLM__EVENTI_ORA_UTC``:

1. **ricerca** — Google News RSS per le parole di ogni pericolo, sugli ultimi
   ``LLM__EVENTI_GIORNI``;
2. **estrazione** — un batch di Claude dice quali titoli raccontano un evento
   nuovo, dove e quando (``EstrattoreEventi``);
3. **verifica**, in codice — due testate diverse e un comune che si risolve.
   Un evento con una testata sola ha una ricerca mirata per comune (la
   ricerca larga trova spesso un articolo per evento: 12 eventi su 15 il
   29 ottobre 2026);
   ogni candidato, verificato o no, resta in ``candidati_eventi``, e un
   evento con una testata sola diventa verità quando ne arriva una seconda;
4. **misura** — ``anticipo.sql`` e le regole dell'esito, le stesse del fact
   check a mano, in ``verifiche_eventi`` (e ``landslide_events`` per le frane).

Gli articoli della pagina pubblica restano manuali: pubblicare chiede una
persona. Il modello scrive solo quali eventi riporta la stampa; punteggi e
soglie non li vede.
"""

from __future__ import annotations

import asyncio
import re
import unicodedata
from collections import Counter
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from limen.agents.chat_agents.estrattore_eventi import (
    NOME_PERICOLO,
    EstrattoreEventi,
    EventoEstratto,
)
from limen.api.dependencies import AppDependencies
from limen.cli.registra_verifica import frana_da_verifica
from limen.config.settings import Settings
from limen.core.logging import get_logger
from limen.core.models.hazard import HazardType
from limen.core.verifiche.esito import esito
from limen.data.repos import anticipo_repo, candidati_eventi_repo, verifiche_eventi_repo
from limen.data.repos.candidati_eventi_repo import Candidato
from limen.data.repos.landslide_events_repo import upsert_many as landslide_upsert
from limen.data.repos.verifiche_eventi_repo import VerificaEvento
from limen.integrations.notizie.google_news import Titolo, cerca

log = get_logger(__name__)

#: Le parole della skill `limen-fact-check`, §1.
PAROLE: dict[HazardType, tuple[str, ...]] = {
    HazardType.LANDSLIDE: ("frana", "smottamento", "colata di fango", "movimento franoso"),
    HazardType.FLOOD: ("alluvione", "esondazione", "allagamenti", "bomba d'acqua"),
    HazardType.WILDFIRE: ("incendio boschivo", "incendio di vegetazione", "Canadair"),
}
#: Le parole della ricerca mirata, una per evento e comune (*Verify*).
PAROLE_VERIFICA: dict[HazardType, tuple[str, ...]] = {
    HazardType.LANDSLIDE: ("frana",),
    HazardType.FLOOD: ("allagamenti", "alluvione"),
    HazardType.WILDFIRE: ("incendio",),
}
_ROMA = ZoneInfo("Europe/Rome")
#: L'ora locale convenzionale di ogni parte del giorno, e la precisione ITALICA.
_ORA = {
    "mattina": (time(9), "T2"),
    "pomeriggio": (time(15), "T2"),
    "sera": (time(20), "T2"),
    "notte": (time(2), "T2"),
    "ignota": (time(12), "T3"),
}


async def titoli_per_pericolo(*, giorni: int, massimi: int) -> dict[HazardType, list[Titolo]]:
    """I titoli di ogni pericolo, senza doppioni, i più recenti per primi."""
    out: dict[HazardType, list[Titolo]] = {}
    for hazard, parole in PAROLE.items():
        risposte: list[list[Titolo]] = await asyncio.gather(
            *(cerca(p, giorni=giorni) for p in parole)
        )
        visti: dict[str, Titolo] = {}
        for t in (t for r in risposte for t in r):
            visti.setdefault(t.url, t)
        out[hazard] = sorted(visti.values(), key=lambda t: t.pubblicato, reverse=True)[:massimi]
    return out


def conferme(e: EventoEstratto, titoli: list[Titolo], testate: set[str]) -> list[Titolo]:
    """I titoli di altre testate che nominano un comune dell'evento, pubblicati
    fra il giorno dell'evento e due giorni dopo: la seconda fonte che la
    ricerca larga non aveva trovato."""
    comuni = [c.casefold() for c in e.comuni]
    return [
        t
        for t in titoli
        if t.testata.strip().casefold() not in testate
        and any(c in t.titolo.casefold() for c in comuni)
        and 0 <= (t.pubblicato.astimezone(_ROMA).date() - e.giorno).days <= 2
    ]


async def cerca_conferme(
    hazard: HazardType, e: EventoEstratto, fonti: list[Titolo]
) -> list[Titolo]:
    """La ricerca mirata per comune, per un evento con una testata sola."""
    testate = {t.testata.strip().casefold() for t in fonti}
    trovati: dict[str, Titolo] = {}
    for comune in e.comuni:
        for parola in PAROLE_VERIFICA[hazard]:
            for t in conferme(e, await cerca(f'"{comune}" {parola}', giorni=7), testate):
                trovati.setdefault(t.url, t)
    return list(trovati.values())


def slug(hazard: HazardType, e: EventoEstratto) -> str:
    """Lo slug della skill: ``AAAA-MM-GG-<pericolo>-<comune>``."""
    ascii_ = unicodedata.normalize("NFKD", e.comuni[0]).encode("ascii", "ignore").decode()
    comune = re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")
    return f"{e.giorno.isoformat()}-{NOME_PERICOLO[hazard]}-{comune}"


def quando(e: EventoEstratto) -> tuple[datetime, str]:
    ora, precisione = _ORA[e.parte]
    return datetime.combine(e.giorno, ora, tzinfo=_ROMA), precisione


def _fonti(titoli: list[Titolo]) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "testata": t.testata,
            "titolo": t.titolo,
            "url": t.url,
            "data": t.pubblicato.date().isoformat(),
        }
        for t in titoli
    )


async def _registra(
    hazard: HazardType, e: EventoEstratto, titoli: list[Titolo], esiti: Counter[str]
) -> None:
    propri = [titoli[i] for i in e.titoli]
    if candidati_eventi_repo.conta_testate(_fonti(propri)) < 2:
        propri += await cerca_conferme(hazard, e, propri)
    fonti = _fonti(propri)
    salvato = await candidati_eventi_repo.fondi(
        Candidato(
            hazard=hazard,
            giorno=e.giorno,
            parte=e.parte,
            luogo=e.luogo,
            regione=e.regione or None,
            nomi_comuni=tuple(e.comuni),
            fonti=fonti,
        )
    )
    if salvato.testate < 2:
        await candidati_eventi_repo.segna(salvato.id, stato="una_testata", comuni=[], slug=None)
        esiti["una_testata"] += 1
        return
    comuni = await candidati_eventi_repo.risolvi_comuni(tuple(e.comuni), e.regione or None)
    if not comuni:
        await candidati_eventi_repo.segna(salvato.id, stato="comune_ignoto", comuni=[], slug=None)
        esiti["comune_ignoto"] += 1
        return

    evento_at, precisione = quando(e)
    misura = await anticipo_repo.misura(
        comuni=comuni,
        hazard=hazard,
        evento_at=evento_at,
        tolleranza_ore=24 if precisione == "T3" else 12,
    )
    risultato, motivo = esito(misura)
    nome = salvato.slug or slug(hazard, e)
    v = VerificaEvento(
        slug=nome,
        hazard=hazard,
        esito=risultato,
        motivo=motivo,
        evento_at=evento_at,
        precisione_ora=precisione,
        luogo=e.luogo,
        regione=e.regione or None,
        comuni=tuple(comuni),
        fonti=salvato.fonti,
        misura=misura,
    )
    luogo = await verifiche_eventi_repo.upsert(v)
    if hazard is HazardType.LANDSLIDE and luogo is not None:
        await landslide_upsert([frana_da_verifica(v, *luogo)])
    await candidati_eventi_repo.segna(salvato.id, stato="verificato", comuni=comuni, slug=nome)
    esiti[risultato] += 1
    log.info("raccolta_eventi.verificato", slug=nome, esito=risultato, motivo=motivo)


async def raccogli(settings: Settings) -> dict[str, Any]:
    llm = settings.llm
    modello = llm.models.eventi.strip()
    # Vuota conta come assente, come per il revisore di fedeltà.
    if "eventi" not in llm.models.model_fields_set or not modello:
        return {"status": "skipped", "reason": "LLM__MODELS__EVENTI non dichiarato"}
    chiave = settings.anthropic_api_key
    if chiave is None or not chiave.get_secret_value().strip():
        return {"status": "skipped", "reason": "ANTHROPIC_API_KEY assente", "model": modello}

    titoli = await titoli_per_pericolo(giorni=llm.eventi_giorni, massimi=llm.eventi_titoli_massimi)
    estratti = await EstrattoreEventi(
        api_key=chiave, model=modello, attesa_massima_s=llm.eventi_attesa_massima_minuti * 60
    ).estrai(titoli)
    esiti: Counter[str] = Counter()
    for hazard, eventi in estratti.items():
        for e in eventi:
            await _registra(hazard, e, titoli[hazard], esiti)
    out: dict[str, Any] = {
        "titoli": {h.value: len(t) for h, t in titoli.items()},
        "estratti": {h.value: len(e) for h, e in estratti.items()},
        **esiti,
    }
    log.info("job.raccolta_eventi.summary", model=modello, **out)
    return out


async def run_raccolta_eventi(deps: AppDependencies) -> dict[str, Any]:
    return await raccogli(deps.settings)
