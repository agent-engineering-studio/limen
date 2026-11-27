"""Fonte e numeri dei dati IdroGEO nei testi di Limen (#671).

Da ispra-idrogeo 0.8 ogni risposta di ``idrogeo-mcp`` porta ``source`` (la
citazione e la licenza giuste: IFFI ed eventi CC BY-SA 4.0, indicatori
CC BY 4.0), e ``ispra_idrogeo.grounding.check_text`` elenca i numeri di un
testo che i dati non sostengono. Qui due funzioni sottili sopra quelle, per
i testi che Limen scrive con dati IdroGEO dentro.

``check_text`` dice che un numero **esiste** nei fatti, non che sia detto
della cosa giusta: «Bari ha 53 frane» passa se 53 è un numero qualunque dei
fatti. Si passano solo i fatti da cui il testo è nato. ``check_claims``
(0.11, #672) legge di cosa è detto un numero e lo confronta con quella cifra:
le sue regole parlano dei nomi dell'API ISPRA, e qui se ne aggiungono per i
nomi dell'affidabilità IFFI (``AffidabilitaIffi``), che è ciò che il
briefing riceve. Solo conteggi: le quote sono frazioni nei fatti e
percentuali nel testo.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ispra_idrogeo.grounding import RULES, Misquote, Rule, check_claims, check_text

_FRANE = ("frana", "frane", "franos", "landslide")
_GIORNO = ("giorno", "day")
#: Prima di quelle della libreria: a parità di parole vince la prima, e la sua
#: ``frane_totali`` non è nei fatti di Limen, quindi non controllerebbe niente.
REGOLE_LIMEN: tuple[Rule, ...] = (
    Rule("frane_al_giorno", (_FRANE, _GIORNO), share=False),
    Rule(
        "frane",
        (_FRANE,),
        share=False,
        # L'esclusione vale per tutta la frase: «giorno» o «dal 2021» qui
        # toglierebbero il totale proprio dalla frase della lettura IFFI.
        without=("resident", "persone", "abitanti", "popolazione", "edific", "km", "event"),
    ),
)


def fonte(risposta: Mapping[str, Any]) -> str | None:
    """Il ``source`` di una risposta di idrogeo-mcp (o ``idrogeo_source``), se c'è."""
    for chiave in ("source", "idrogeo_source"):
        valore = risposta.get(chiave)
        if isinstance(valore, str) and valore.strip():
            return valore.strip()
    return None


def numeri_non_trovati(testo: str, fatti: Any, domanda: str = "") -> list[str]:
    """I numeri e le date di ``testo`` che nessun numero di ``fatti`` sostiene.

    ``domanda`` è il testo da cui si è partiti (la richiesta, il messaggio al
    modello): i numeri che ci sono valgono anche loro. Vuota = tutto trovato.
    """
    return check_text(testo, fatti, domanda)


def numeri_attribuiti_male(testo: str, fatti: Any) -> list[Misquote]:
    """I numeri di ``testo`` detti di una cifra di ``fatti`` che non è la loro.

    «Bari ha 4.038 frane» quando 4.038 nei fatti sono le frane datate al
    giorno: ``numeri_non_trovati`` lo lascia passare, questa no. Vuota = niente
    di attribuito male; un numero che non sa collocare lo lascia all'altra.
    """
    return check_claims(testo, fatti, (*REGOLE_LIMEN, *RULES))


__all__ = ["REGOLE_LIMEN", "fonte", "numeri_attribuiti_male", "numeri_non_trovati"]
