"""La traduzione inglese delle spiegazioni regionali, controllata sui numeri.

Il racconto italiano lo scrive l'AI dai numeri del motore; l'inglese ne è la
traduzione e non una seconda stesura: un secondo racconto dagli stessi dati
costerebbe il doppio dei token d'ingresso e potrebbe dire cose diverse in
due lingue. Tradurre costa una frazione, e il contenuto resta uno.

La traduzione non è autorevole più dell'originale, e si accetta solo se
porta **esattamente** gli stessi numeri: un valore cambiato, aggiunto o perso
è il guasto che conta, perché è l'unico che un lettore non vede. Il confronto
legge i numeri secondo la lingua — `23.214` e `0,45` in italiano sono
`23,214` e `0.45` in inglese — perché il controllo dei racconti italiani
(`fedelta.controllo_numeri`) prenderebbe `23,214` per un numero inventato.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from functools import cache
from importlib import resources

from pydantic import BaseModel, ConfigDict, ValidationError

from limen.agents.chat_agents.prompts_registry import PROMPT_PACKAGE
from limen.agents.llm_factory.base import ChatClient, ChatMessage
from limen.core.logging import get_logger

log = get_logger(__name__)

_NUMERO = re.compile(r"\d+(?:[.,]\d+)*")


class Traduzione(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    testo: str
    anomalies: list[str]


@cache
def _system_prompt() -> str:
    return resources.files(PROMPT_PACKAGE).joinpath("traduzione.en.md").read_text(encoding="utf-8")


def numeri(testo: str, lingua: str) -> list[Decimal]:
    """I numeri di un testo, letti con le convenzioni della sua lingua.

    Il separatore delle migliaia della lingua (il punto in italiano, la
    virgola in inglese) vale come tale solo davanti a esattamente tre cifre;
    altrimenti è un decimale. Così `0.81`, che i testi italiani a volte
    scrivono col punto, resta 0,81 e non diventa 81.
    """
    migliaia = "." if lingua == "it" else ","
    out: list[Decimal] = []
    for m in _NUMERO.finditer(testo):
        pezzi = re.split(r"([.,])", m.group(0))
        cifre = pezzi[0]
        for sep, gruppo in zip(pezzi[1::2], pezzi[2::2], strict=True):
            cifre += gruppo if sep == migliaia and len(gruppo) == 3 else "." + gruppo
        try:
            out.append(Decimal(cifre).normalize())
        except InvalidOperation:
            continue
    return out


def letture(token: str) -> frozenset[Decimal]:
    """I valori che un numero scritto può avere, in qualunque delle due lingue.

    I racconti dell'AI non seguono una convenzione: in italiano scrivono
    spesso i punteggi col punto, copiati dai dati (`0.374`, «combustibile
    1.000» per 1,0). Un separatore seguito da tre cifre può quindi essere
    delle migliaia o un decimale, e le due letture valgono entrambe; uno `0`
    iniziale non regge mai delle migliaia.
    """
    pezzi = re.split(r"[.,]", token)
    out: set[Decimal] = set()
    testa, gruppi = pezzi[0], pezzi[1:]
    if not gruppi:
        return frozenset({Decimal(testa).normalize()})
    if testa != "0" and len(testa) <= 3 and all(len(g) == 3 for g in gruppi):
        out.add(Decimal(testa + "".join(gruppi)).normalize())
    if all(len(g) == 3 for g in gruppi[:-1]) and (len(gruppi) == 1 or testa != "0"):
        out.add(Decimal(testa + "".join(gruppi[:-1]) + "." + gruppi[-1]).normalize())
    return frozenset(out)


def numeri_coincidono(italiano: str, inglese: str) -> bool:
    """Gli stessi numeri, con le stesse ripetizioni, in un ordine qualunque.

    Ogni numero della traduzione deve corrispondere a uno dell'originale con
    almeno una lettura in comune, e nessuno dei due testi può averne di più.
    """
    originale = [letture(m.group(0)) for m in _NUMERO.finditer(italiano)]
    resa = [letture(m.group(0)) for m in _NUMERO.finditer(inglese)]
    if len(originale) != len(resa):
        return False
    liberi = list(originale)
    # I più vincolati per primi: un numero con una sola lettura non deve
    # perdere il suo corrispondente a vantaggio di uno che ne ha due.
    for valori in sorted(resa, key=len):
        k = next((k for k, cand in enumerate(liberi) if cand & valori), None)
        if k is None:
            return False
        liberi.pop(k)
    return True


class TraduttoreRacconti:
    """Traduce in inglese una spiegazione e le anomalie della sua analisi."""

    def __init__(self, client: ChatClient) -> None:
        self._client = client

    async def traduci(self, testo: str, anomalie: list[str]) -> Traduzione | None:
        """La traduzione, o ``None`` se il modello non ne ha data una fedele."""
        messages = [
            ChatMessage(role="system", content=_system_prompt()),
            ChatMessage(
                role="user",
                content=f"TESTO:\n{testo}\n\nANOMALIE:\n{json.dumps(anomalie, ensure_ascii=False)}",
            ),
        ]
        try:
            raw = await self._client.chat(messages, response_format="json_object")
        except Exception as exc:
            log.warning("traduzione.chat_error", error=str(exc), error_type=type(exc).__name__)
            return None
        try:
            tradotta = Traduzione.model_validate_json(raw)
        except (ValidationError, json.JSONDecodeError) as exc:
            log.warning("traduzione.non_valida", error=str(exc), raw=raw[:300])
            return None
        originale = " ".join([testo, *anomalie])
        resa = " ".join([tradotta.testo, *tradotta.anomalies])
        if len(tradotta.anomalies) != len(anomalie) or not numeri_coincidono(originale, resa):
            log.warning(
                "traduzione.numeri_diversi",
                italiano=[str(n) for n in numeri(originale, "it")],
                inglese=[str(n) for n in numeri(resa, "en")],
            )
            return None
        return tradotta


__all__ = ["TraduttoreRacconti", "Traduzione", "numeri", "numeri_coincidono"]
