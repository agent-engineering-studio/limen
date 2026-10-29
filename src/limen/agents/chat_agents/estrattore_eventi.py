"""L'estrattore: quali eventi reali raccontano i titoli della stampa (#347).

Il primo passo della verifica di Step-DeepResearch (*Extract*): dai titoli di
Google News, cercati per parola, un modello tira fuori gli eventi nuovi —
pericolo, giorno, comuni, quali titoli li raccontano — e scarta allerte,
lavori e anniversari. Non decide che un evento è verità: lo decidono, in
codice, le due testate diverse e il comune che si risolve.

Come il revisore di fedeltà, un solo Message Batch, uno per pericolo: la
raccolta è quotidiana e nessuno aspetta, e in batch costa la metà. Il modello
non tocca niente del motore: scrive solo quali eventi riporta la stampa.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping, Sequence
from datetime import date
from functools import cache
from importlib import resources
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError

from limen.agents.chat_agents.prompts_registry import PROMPT_PACKAGE
from limen.core.logging import get_logger
from limen.core.models.hazard import HazardType
from limen.integrations.notizie.google_news import Titolo

if TYPE_CHECKING:
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages import MessageBatchIndividualResponse

log = get_logger(__name__)

NOME_PERICOLO = {
    HazardType.LANDSLIDE: "frana",
    HazardType.FLOOD: "alluvione",
    HazardType.WILDFIRE: "incendio",
}


@cache
def _load_system_prompt() -> str:
    return (
        resources.files(PROMPT_PACKAGE)
        .joinpath("estrattore_eventi.it.md")
        .read_text(encoding="utf-8")
    )


class EventoEstratto(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    giorno: date
    parte: Literal["mattina", "pomeriggio", "sera", "notte", "ignota"]
    luogo: str
    comuni: list[str]
    regione: str
    titoli: list[int]


class _Risposta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eventi: list[EventoEstratto]


def elenco(titoli: Sequence[Titolo]) -> str:
    return "\n".join(
        f"[{i}] ({t.testata}, {t.pubblicato.date().isoformat()}) {t.titolo}"
        for i, t in enumerate(titoli)
    )


class EstrattoreEventi:
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

    async def estrai(
        self, titoli: Mapping[HazardType, Sequence[Titolo]]
    ) -> dict[HazardType, list[EventoEstratto]]:
        """Gli eventi di ogni pericolo; un pericolo senza risposta valida non
        ha voce nel risultato, che non è «nessun evento»."""
        import anthropic

        pericoli = [h for h, t in titoli.items() if t]
        out: dict[HazardType, list[EventoEstratto]] = {}
        if not pericoli:
            return out
        try:
            batch = await self._client.messages.batches.create(
                requests=[
                    {"custom_id": h.value, "params": self._params(h, titoli[h])} for h in pericoli
                ]
            )
            scadenza = time.monotonic() + self._attesa_massima_s
            while batch.processing_status != "ended":
                if time.monotonic() >= scadenza:
                    log.warning("estrattore_eventi.batch_scaduto", batch_id=batch.id)
                    await self._client.messages.batches.cancel(batch.id)
                    return out
                await asyncio.sleep(self._intervallo_s)
                batch = await self._client.messages.batches.retrieve(batch.id)
            async for r in await self._client.messages.batches.results(batch.id):
                eventi = _eventi(r, len(titoli[HazardType(r.custom_id)]))
                if eventi is not None:
                    out[HazardType(r.custom_id)] = eventi
        except anthropic.APIError as exc:
            log.warning(
                "estrattore_eventi.non_risponde", error=str(exc), error_type=type(exc).__name__
            )
        return out

    def _params(
        self, hazard: HazardType, titoli: Sequence[Titolo]
    ) -> MessageCreateParamsNonStreaming:
        return {
            "model": self._model,
            "max_tokens": 16000,
            "system": _load_system_prompt(),
            "messages": [
                {
                    "role": "user",
                    "content": f"PERICOLO: {NOME_PERICOLO[hazard]}\n\nTITOLI:\n{elenco(titoli)}",
                }
            ],
            "output_config": {"format": {"type": "json_schema", "schema": _SCHEMA}},
        }


_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "eventi": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "giorno": {"type": "string", "format": "date"},
                    "parte": {
                        "type": "string",
                        "enum": ["mattina", "pomeriggio", "sera", "notte", "ignota"],
                    },
                    "luogo": {"type": "string"},
                    "comuni": {"type": "array", "items": {"type": "string"}},
                    "regione": {"type": "string"},
                    "titoli": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["giorno", "parte", "luogo", "comuni", "regione", "titoli"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["eventi"],
    "additionalProperties": False,
}


def _eventi(r: MessageBatchIndividualResponse, n_titoli: int) -> list[EventoEstratto] | None:
    if r.result.type != "succeeded":
        log.warning("estrattore_eventi.richiesta_fallita", hazard=r.custom_id, esito=r.result.type)
        return None
    msg = r.result.message
    raw = next((b.text for b in msg.content if b.type == "text"), None)
    if msg.stop_reason != "end_turn" or raw is None:
        log.warning("estrattore_eventi.risposta_mancante", stop_reason=msg.stop_reason)
        return None
    try:
        eventi = _Risposta.model_validate_json(raw).eventi
    except ValidationError as exc:
        log.warning("estrattore_eventi.risposta_non_valida", error=str(exc), raw=raw[:300])
        return None
    # Un numero di titolo che non esiste è un'invenzione: l'evento non ha fonti.
    return [
        e.model_copy(update={"titoli": [i for i in e.titoli if 0 <= i < n_titoli]})
        for e in eventi
        if e.comuni and any(0 <= i < n_titoli for i in e.titoli)
    ]


__all__ = ["NOME_PERICOLO", "EstrattoreEventi", "EventoEstratto", "elenco"]
