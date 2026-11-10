"""Il riepilogo notturno sulla qualità dei dati, detto in parole dall'AI (#421).

Le righe del riepilogo le scrive il codice (`core/qualita_dati.py`), e restano
nel report: il modello ne fa un paragrafo per chi legge al mattino — che cosa
è rotto, da quando, che cosa guardare per primo — e non le sostituisce. Vale la
regola di tutti i testi di Limen: l'AI scrive parole, mai numeri. Un paragrafo
con una cifra che le righe non contengono si scarta, e il report esce con le
sole righe.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import cache
from importlib import resources

from limen.agents.chat_agents.prompts_registry import PROMPT_PACKAGE
from limen.agents.chat_agents.traduttore import numeri_dentro
from limen.agents.llm_factory.base import ChatClient, ChatMessage
from limen.core.logging import get_logger

log = get_logger(__name__)

#: Il prompt chiede al massimo 120 parole: il margine copre l'italiano.
_MAX_TOKENS = 400


@cache
def _system_prompt() -> str:
    return (
        resources.files(PROMPT_PACKAGE).joinpath("qualita_dati.it.md").read_text(encoding="utf-8")
    )


async def riformula(client: ChatClient, righe: Sequence[str]) -> str | None:
    """Il paragrafo, o ``None`` se il modello non risponde o mette un numero suo."""
    elenco = "\n".join(f"- {r}" for r in righe)
    messages = [
        ChatMessage(role="system", content=_system_prompt()),
        ChatMessage(role="user", content=elenco),
    ]
    try:
        risposta = await client.chat(messages, max_tokens=_MAX_TOKENS)
    except Exception as exc:
        log.warning("qualita_dati.ai_errore", error=str(exc), error_type=type(exc).__name__)
        return None
    paragrafo = " ".join(risposta.split())
    if not paragrafo:
        return None
    if not numeri_dentro(paragrafo, elenco):
        log.warning("qualita_dati.ai_numeri", testo=paragrafo[:300])
        return None
    return paragrafo


__all__ = ["riformula"]
