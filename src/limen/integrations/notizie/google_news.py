"""Google News RSS: i titoli della stampa italiana per una parola, senza chiave.

È la ricerca del fact check (#347): trova i titoli, non decide niente. Che un
titolo racconti un evento nuovo, e dove, lo stabilisce l'estrattore; che
l'evento sia verità, le due testate diverse. Un titolo porta la testata in
``<source>``, ed è quella — non il dominio del link, che è sempre
``news.google.com`` — a dire se due fonti sono indipendenti.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import httpx
from tenacity import RetryError

from limen.core.logging import get_logger
from limen.integrations._http import fetch_with_retry

log = get_logger(__name__)

URL = "https://news.google.com/rss/search"


@dataclass(frozen=True, slots=True)
class Titolo:
    titolo: str
    testata: str
    url: str
    pubblicato: datetime


def leggi_rss(xml: str) -> list[Titolo]:
    """I titoli di una risposta RSS; un elemento senza data o testata si salta."""
    out: list[Titolo] = []
    for item in ElementTree.fromstring(xml).iter("item"):
        titolo = (item.findtext("title") or "").strip()
        testata = (item.findtext("source") or "").strip()
        data = item.findtext("pubDate")
        if not titolo or not testata or not data:
            continue
        # Google aggiunge « - Testata» in coda al titolo: è già in <source>.
        titolo = titolo.removesuffix(f" - {testata}").strip()
        out.append(
            Titolo(
                titolo=titolo,
                testata=testata,
                url=(item.findtext("link") or "").strip(),
                pubblicato=parsedate_to_datetime(data),
            )
        )
    return out


async def cerca(parola: str, *, giorni: int) -> list[Titolo]:
    """I titoli degli ultimi ``giorni`` che contengono ``parola``, in italiano.

    Una ricerca che non risponde è una lista vuota, non un errore: gli altri
    pericoli e le altre parole vanno avanti.
    """
    try:
        risposta = await fetch_with_retry(
            "GET",
            URL,
            params={"q": f"{parola} when:{giorni}d", "hl": "it", "gl": "IT", "ceid": "IT:it"},
        )
        risposta.raise_for_status()
        return leggi_rss(risposta.text)
    except (httpx.HTTPError, RetryError, ElementTree.ParseError) as exc:
        log.warning(
            "integration.degraded",
            label="notizie.google_news",
            parola=parola,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return []
