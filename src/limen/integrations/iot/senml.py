"""SenML (RFC 8428) per il protocollo v2 dei sensori (#252).

Un messaggio su ``limen/v2/{id}/obs`` è un array SenML JSON:

    [{"bn": "pluvio-matera-01/", "bt": 1792065600,
      "n": "rainfall", "u": "mm", "v": 0.4},
     {"n": "seq", "v": 18342}]

Si accetta un sottoinsieme stretto della RFC, perché ogni campo in più è un
dato di cui fidarsi:

* il nome risolto (``bn`` + ``n``) deve essere ``{id}/{grandezza}``, con
  l'id del **topic** — che l'ACL del broker lega al CN del certificato. Un
  messaggio che parla a nome di un altro dispositivo si scarta;
* l'unità è fissa: quella canonica della grandezza, niente conversioni;
* il tempo è UTC in secondi (``bt`` + ``t``); sotto 2**28 è relativo
  all'arrivo, come vuole la RFC;
* ogni messaggio porta un record ``seq`` con un intero non negativo;
* una grandezza che Limen non conosce si ignora, così un firmware più nuovo
  non viene rifiutato per intero;
* i campi che la RFC dichiara da capire per forza (quelli che finiscono con
  ``_``) fanno scartare il messaggio; gli altri campi sconosciuti si ignorano.

Il parser è puro: nessun I/O, nessun orologio letto da qui.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from limen.integrations.iot.schemas import CANONICAL_UNITS, ObservedProperty

# RFC 8428 §4.5.3: un tempo sotto 2**28 secondi è relativo all'istante attuale.
_TEMPO_RELATIVO_SOTTO = 2**28
_SEQ = "seq"


class SenmlError(ValueError):
    """Messaggio SenML da scartare per intero."""


@dataclass(frozen=True, slots=True)
class Misura:
    grandezza: ObservedProperty
    valore: float
    unita: str
    istante: datetime


@dataclass(frozen=True, slots=True)
class MessaggioV2:
    sequenza: int
    misure: tuple[Misura, ...]
    ignorate: tuple[str, ...]


def _numero(record: dict[str, Any], campo: str) -> float | None:
    valore = record.get(campo)
    if valore is None:
        return None
    # bool è un int per Python, non per SenML.
    if isinstance(valore, bool) or not isinstance(valore, int | float):
        raise SenmlError(f"{campo} non numerico")
    if not math.isfinite(valore):
        raise SenmlError(f"{campo} non finito")
    return float(valore)


def _testo(record: dict[str, Any], campo: str) -> str | None:
    valore = record.get(campo)
    if valore is None:
        return None
    if not isinstance(valore, str):
        raise SenmlError(f"{campo} non è una stringa")
    return valore


def analizza(payload: bytes, *, device_id: str, ricevuto: datetime) -> MessaggioV2:
    """Traduce un payload SenML JSON nelle misure del dispositivo ``device_id``.

    Solleva :class:`SenmlError` se il messaggio va scartato per intero.
    """
    try:
        records = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SenmlError("JSON non valido") from exc
    if not isinstance(records, list) or not records:
        raise SenmlError("serve un array SenML non vuoto")

    prefisso = f"{device_id}/"
    bn = ""
    bt = 0.0
    bu: str | None = None
    sequenza: int | None = None
    misure: list[Misura] = []
    ignorate: list[str] = []

    for record in records:
        if not isinstance(record, dict):
            raise SenmlError("ogni record deve essere un oggetto")
        if any(k.endswith("_") for k in record):
            raise SenmlError("campo obbligatorio da capire non supportato")
        # I campi base valgono per i record che seguono (RFC 8428 §4.1).
        if (nuovo_bn := _testo(record, "bn")) is not None:
            bn = nuovo_bn
        if (nuovo_bt := _numero(record, "bt")) is not None:
            bt = nuovo_bt
        if (nuova_bu := _testo(record, "bu")) is not None:
            bu = nuova_bu

        nome = bn + (_testo(record, "n") or "")
        if not nome.startswith(prefisso):
            raise SenmlError("il nome non appartiene al dispositivo del topic")
        grandezza = nome[len(prefisso) :]
        valore = _numero(record, "v")
        if valore is None:
            raise SenmlError(f"{grandezza or 'record'} senza valore")

        if grandezza == _SEQ:
            if sequenza is not None:
                raise SenmlError("seq ripetuto")
            if not valore.is_integer() or valore < 0:
                raise SenmlError("seq deve essere un intero non negativo")
            sequenza = int(valore)
            continue

        try:
            proprieta = ObservedProperty(grandezza)
        except ValueError:
            ignorate.append(grandezza)
            continue

        unita = _testo(record, "u") or bu
        if unita != CANONICAL_UNITS[proprieta]:
            raise SenmlError(f"{grandezza}: unità {unita!r}, attesa {CANONICAL_UNITS[proprieta]!r}")

        tempo = bt + (_numero(record, "t") or 0.0)
        try:
            istante = (
                ricevuto + timedelta(seconds=tempo)
                if abs(tempo) < _TEMPO_RELATIVO_SOTTO
                else datetime.fromtimestamp(tempo, tz=UTC)
            )
        except (OverflowError, OSError, ValueError) as exc:
            raise SenmlError(f"{grandezza}: tempo fuori scala") from exc
        misure.append(Misura(grandezza=proprieta, valore=valore, unita=unita, istante=istante))

    if sequenza is None:
        raise SenmlError("manca il record seq")
    return MessaggioV2(sequenza=sequenza, misure=tuple(misure), ignorate=tuple(ignorate))


__all__ = ["MessaggioV2", "Misura", "SenmlError", "analizza"]
