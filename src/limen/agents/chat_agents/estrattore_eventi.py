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
from dataclasses import dataclass
from datetime import date
from functools import cache
from importlib import resources
from typing import TYPE_CHECKING, Any, Literal
from zoneinfo import ZoneInfo

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
def _prompt(nome: str) -> str:
    return resources.files(PROMPT_PACKAGE).joinpath(nome).read_text(encoding="utf-8")


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


class _Conferma(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titoli: list[int]


_ROMA = ZoneInfo("Europe/Rome")


def elenco(titoli: Sequence[Titolo]) -> str:
    # Il giorno di uscita in ora italiana: il modello ci data «ieri» e i
    # titoli senza data, e `quando` legge il giorno come ora di Roma.
    return "\n".join(
        f"[{i}] ({t.testata}, {t.pubblicato.astimezone(_ROMA).date().isoformat()}) {t.titolo}"
        for i, t in enumerate(titoli)
    )


@dataclass(frozen=True, slots=True)
class Consumo:
    batch_id: str
    input_tokens: int
    output_tokens: int


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
        #: Un consumo per batch finito: il job li scrive in `spesa_llm`.
        self.consumi: list[Consumo] = []

    async def estrai(
        self, titoli: Mapping[HazardType, Sequence[Titolo]]
    ) -> dict[HazardType, list[EventoEstratto]]:
        """Gli eventi di ogni pericolo; un pericolo senza risposta valida non
        ha voce nel risultato, che non è «nessun evento»."""
        pericoli = [h for h, t in titoli.items() if t]
        risposte = await self._esegui(
            {
                h.value: self._params(
                    "estrattore_eventi.it.md",
                    f"PERICOLO: {NOME_PERICOLO[h]}\n\nTITOLI:\n{elenco(titoli[h])}",
                    _SCHEMA,
                )
                for h in pericoli
            }
        )
        out: dict[HazardType, list[EventoEstratto]] = {}
        for h in pericoli:
            eventi = _eventi(risposte.get(h.value), len(titoli[h]))
            if eventi is not None:
                out[h] = eventi
        return out

    async def conferma(
        self, casi: Sequence[tuple[HazardType, EventoEstratto, Sequence[Titolo]]]
    ) -> list[list[int]]:
        """Per ogni evento, quali dei titoli trovati con la ricerca mirata
        raccontano proprio quello: il *Verify* di Step-DeepResearch. Nessuna
        risposta vale «nessuna conferma», mai «tutte»."""
        risposte = await self._esegui(
            {
                f"c{i}": self._params(
                    "conferma_eventi.it.md",
                    f"EVENTO: {NOME_PERICOLO[h]} del {e.giorno.isoformat()} a {e.luogo} "
                    f"({', '.join(e.comuni)})\n\nTITOLI:\n{elenco(t)}",
                    _SCHEMA_CONFERMA,
                )
                for i, (h, e, t) in enumerate(casi)
            }
        )
        out: list[list[int]] = []
        for i, (_, _, t) in enumerate(casi):
            raw = risposte.get(f"c{i}")
            try:
                scelti = _Conferma.model_validate_json(raw).titoli if raw else []
            except ValidationError as exc:
                log.warning("estrattore_eventi.conferma_non_valida", error=str(exc))
                scelti = []
            out.append(sorted({j for j in scelti if 0 <= j < len(t)}))
        return out

    async def _esegui(
        self, richieste: dict[str, MessageCreateParamsNonStreaming]
    ) -> dict[str, str]:
        """Un Message Batch; il testo di ogni risposta riuscita, per custom_id."""
        import anthropic

        testi: dict[str, str] = {}
        if not richieste:
            return testi
        try:
            batch = await self._client.messages.batches.create(
                requests=[{"custom_id": k, "params": p} for k, p in richieste.items()]
            )
            scadenza = time.monotonic() + self._attesa_massima_s
            annullato = False
            while batch.processing_status != "ended":
                if time.monotonic() >= scadenza:
                    if annullato:
                        log.warning("estrattore_eventi.batch_non_chiuso", batch_id=batch.id)
                        return testi
                    # Le richieste già riuscite restano pagate anche annullando
                    # il resto: si aspetta la chiusura e se ne leggono i token.
                    log.warning("estrattore_eventi.batch_scaduto", batch_id=batch.id)
                    await self._client.messages.batches.cancel(batch.id)
                    annullato = True
                    scadenza = time.monotonic() + self._attesa_massima_s
                await asyncio.sleep(self._intervallo_s)
                batch = await self._client.messages.batches.retrieve(batch.id)
            ingresso = uscita = 0
            async for r in await self._client.messages.batches.results(batch.id):
                if r.result.type == "succeeded":
                    ingresso += r.result.message.usage.input_tokens
                    uscita += r.result.message.usage.output_tokens
                testo = _testo(r)
                if testo is not None:
                    testi[r.custom_id] = testo
            self.consumi.append(Consumo(batch.id, ingresso, uscita))
            log.info(
                "estrattore_eventi.usage",
                batch_id=batch.id,
                input_tokens=ingresso,
                output_tokens=uscita,
            )
        except anthropic.APIError as exc:
            log.warning(
                "estrattore_eventi.non_risponde", error=str(exc), error_type=type(exc).__name__
            )
        return testi

    def _params(
        self, prompt: str, contenuto: str, schema: dict[str, Any]
    ) -> MessageCreateParamsNonStreaming:
        return {
            "model": self._model,
            "max_tokens": 16000,
            "system": _prompt(prompt),
            "messages": [{"role": "user", "content": contenuto}],
            "output_config": {"format": {"type": "json_schema", "schema": schema}},
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


_SCHEMA_CONFERMA: dict[str, Any] = {
    "type": "object",
    "properties": {"titoli": {"type": "array", "items": {"type": "integer"}}},
    "required": ["titoli"],
    "additionalProperties": False,
}


def _testo(r: MessageBatchIndividualResponse) -> str | None:
    if r.result.type != "succeeded":
        log.warning(
            "estrattore_eventi.richiesta_fallita", custom_id=r.custom_id, esito=r.result.type
        )
        return None
    msg = r.result.message
    raw = next((b.text for b in msg.content if b.type == "text"), None)
    if msg.stop_reason != "end_turn" or raw is None:
        log.warning("estrattore_eventi.risposta_mancante", stop_reason=msg.stop_reason)
        return None
    return raw


def _eventi(raw: str | None, n_titoli: int) -> list[EventoEstratto] | None:
    if raw is None:
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
