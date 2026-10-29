"""Il revisore: la spiegazione dell'AI è fedele ai dati da cui è nata?

Due controlli, in quest'ordine:

1. **deterministico** (`briefing_eval`): ogni numero del testo deve stare nel
   messaggio che il modello ha ricevuto, più le regole del prompt (lunghezza,
   niente elenchi, niente termini d'allarme). Non costa niente e non sbaglia;
2. **un secondo modello**, diverso da quello che ha scritto, per quello che
   una regex non vede: una causa sbagliata, un luogo inventato, un evento
   futuro dato per certo. Le spiegazioni le scrive Haiku; il revisore è
   Sonnet, via Message Batches: nessuno aspetta il verdetto, e in batch
   costa la metà.

Il revisore non tocca niente: non riscrive il testo e tanto meno i numeri.
Scrive un verdetto accanto alla spiegazione e un warning nei log, e chi
decide cosa farne è una persona. Un revisore che non risponde lascia il
giudizio a ``None`` — mai «fedele» per difetto.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from functools import cache
from importlib import resources
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from limen.agents.chat_agents.briefing_eval import (
    BriefingEval,
    allowed_numbers_from_text,
    evaluate_briefing,
)
from limen.agents.chat_agents.prompts_registry import PROMPT_PACKAGE
from limen.agents.grounding.format import senza_citazioni
from limen.core.logging import get_logger

if TYPE_CHECKING:
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages import MessageBatchIndividualResponse

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
    """Il secondo modello, su tutto il campione in un solo batch."""

    def __init__(
        self,
        *,
        api_key: SecretStr,
        model: str,
        attesa_massima_s: float,
        intervallo_s: float = 60.0,
    ) -> None:
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=api_key.get_secret_value())
        self._model = model
        self._attesa_massima_s = attesa_massima_s
        self._intervallo_s = intervallo_s

    async def giudica(self, coppie: Sequence[tuple[str, str]]) -> list[Giudizio | None]:
        """Un giudizio per ogni ``(testo, ingresso)``, nello stesso ordine.

        ``None`` dove il revisore non ne ha dato uno: un batch che non parte,
        che non finisce entro l'attesa, una richiesta in errore o un rifiuto.
        Nessun secondo tentativo: un verdetto mancante è un'informazione
        accettabile — il controllo deterministico c'è già.
        """
        import anthropic

        giudizi: list[Giudizio | None] = [None] * len(coppie)
        try:
            batch = await self._client.messages.batches.create(
                requests=[
                    {"custom_id": f"s{i}", "params": self._params(testo, ingresso)}
                    for i, (testo, ingresso) in enumerate(coppie)
                ]
            )
            scadenza = time.monotonic() + self._attesa_massima_s
            while batch.processing_status != "ended":
                if time.monotonic() >= scadenza:
                    log.warning("fedelta.batch_scaduto", batch_id=batch.id)
                    await self._client.messages.batches.cancel(batch.id)
                    return giudizi
                await asyncio.sleep(self._intervallo_s)
                batch = await self._client.messages.batches.retrieve(batch.id)
            async for r in await self._client.messages.batches.results(batch.id):
                giudizi[int(r.custom_id[1:])] = _giudizio(r)
        except anthropic.APIError as exc:
            log.warning(
                "fedelta.revisore_non_risponde",
                error=str(exc),
                error_type=type(exc).__name__,
            )
        return giudizi

    def _params(self, testo: str, ingresso: str) -> MessageCreateParamsNonStreaming:
        return {
            "model": self._model,
            # Il ragionamento conta nel tetto: 400 token bastano al JSON, non
            # al pensiero che lo precede.
            "max_tokens": 16000,
            "system": _load_system_prompt(),
            "messages": [
                {
                    "role": "user",
                    "content": f"DATI:\n{ingresso}\n\nTESTO:\n{senza_citazioni(testo)}",
                }
            ],
            "output_config": {"format": {"type": "json_schema", "schema": _SCHEMA}},
        }


# Il tetto dei cinque problemi resta a `Giudizio`: lo schema degli output
# strutturati non accetta `maxItems`.
_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "fedele": {"type": "boolean"},
        "problemi": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["fedele", "problemi"],
    "additionalProperties": False,
}


def _giudizio(r: MessageBatchIndividualResponse) -> Giudizio | None:
    if r.result.type != "succeeded":
        log.warning("fedelta.richiesta_fallita", esito=r.result.type)
        return None
    msg = r.result.message
    raw = next((b.text for b in msg.content if b.type == "text"), None)
    if msg.stop_reason != "end_turn" or raw is None:
        log.warning("fedelta.giudizio_mancante", stop_reason=msg.stop_reason)
        return None
    try:
        return Giudizio.model_validate_json(raw)
    except ValidationError as exc:
        log.warning("fedelta.giudizio_non_valido", error=str(exc), raw=raw[:300])
        return None


__all__ = ["Giudizio", "RevisoreFedelta", "controllo_numeri"]
