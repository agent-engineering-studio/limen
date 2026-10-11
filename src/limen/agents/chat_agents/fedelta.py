"""Il revisore: la spiegazione dell'AI è fedele ai dati da cui è nata?

Due controlli, in quest'ordine:

1. **deterministico** (`briefing_eval`): ogni numero del testo deve stare nel
   messaggio che il modello ha ricevuto, più le regole del prompt (lunghezza,
   niente elenchi, niente termini d'allarme). Non costa niente e non sbaglia;
2. **un secondo modello**, di un'altra famiglia, per quello che una regex non
   vede: una causa sbagliata, un luogo inventato, un evento futuro dato per
   certo. Gira sul modello lento (GLM-5.2) di sera, su un campione.

Il revisore non tocca niente: non riscrive il testo e tanto meno i numeri.
Scrive un verdetto accanto alla spiegazione e un warning nei log, e chi
decide cosa farne è una persona. Un revisore che non risponde lascia il
giudizio a ``None`` — mai «fedele» per difetto.
"""

from __future__ import annotations

import json
from functools import cache
from importlib import resources

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from limen.agents.chat_agents.briefing_eval import (
    BriefingEval,
    allowed_numbers_from_text,
    evaluate_briefing,
)
from limen.agents.chat_agents.prompts_registry import PROMPT_PACKAGE
from limen.agents.grounding.format import senza_citazioni
from limen.agents.llm_factory.base import ChatClient, ChatMessage
from limen.core.logging import get_logger

log = get_logger(__name__)


@cache
def _load_system_prompt() -> str:
    return resources.files(PROMPT_PACKAGE).joinpath("fedelta.it.md").read_text(encoding="utf-8")


class Giudizio(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fedele: bool
    problemi: list[str] = Field(default_factory=list, max_length=5)


def controllo_numeri(testo: str, ingresso: str) -> BriefingEval:
    """Il controllo deterministico, sul racconto senza citazioni."""
    return evaluate_briefing(
        senza_citazioni(testo), allowed_numbers=allowed_numbers_from_text(ingresso)
    )


class RevisoreFedelta:
    role_name = "Fedelta"

    def __init__(self, client: ChatClient) -> None:
        self._client = client

    async def giudica(self, testo: str, ingresso: str) -> Giudizio | None:
        """Il giudizio del secondo modello, o ``None`` se non ne ha dato uno.

        Nessun secondo tentativo di riparazione, a differenza del RiskAnalyst:
        sul modello lento costerebbe un'altra mezz'ora, e un verdetto mancante
        è un'informazione accettabile — il controllo deterministico c'è già.
        """
        messages = [
            ChatMessage(role="system", content=_load_system_prompt()),
            ChatMessage(
                role="user",
                content=f"DATI:\n{ingresso}\n\nTESTO:\n{senza_citazioni(testo)}",
            ),
        ]
        try:
            raw = await self._client.chat(messages, response_format="json_object", max_tokens=400)
        except Exception as exc:
            log.warning(
                "fedelta.revisore_non_risponde",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return None
        try:
            return Giudizio.model_validate_json(raw)
        except (ValidationError, json.JSONDecodeError) as exc:
            log.warning("fedelta.giudizio_non_valido", error=str(exc), raw=raw[:300])
            return None


__all__ = ["Giudizio", "RevisoreFedelta", "controllo_numeri"]
