"""Fonte e numeri dei dati IdroGEO nei testi di Limen (#671).

Da ispra-idrogeo 0.8 ogni risposta di ``idrogeo-mcp`` porta ``source`` (la
citazione e la licenza giuste: IFFI ed eventi CC BY-SA 4.0, indicatori
CC BY 4.0), e ``ispra_idrogeo.grounding.check_text`` elenca i numeri di un
testo che i dati non sostengono. Qui due funzioni sottili sopra quelle, per
i testi che Limen scrive con dati IdroGEO dentro.

``check_text`` dice che un numero **esiste** nei fatti, non che sia detto
della cosa giusta: «Bari ha 53 frane» passa se 53 è un numero qualunque dei
fatti. Si passano solo i fatti da cui il testo è nato.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ispra_idrogeo.grounding import check_text


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


__all__ = ["fonte", "numeri_non_trovati"]
