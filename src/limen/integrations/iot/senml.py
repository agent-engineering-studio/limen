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

Su LoRaWAN lo stesso messaggio viaggia in CBOR (RFC 8428 §6, #266):
:func:`cbor_a_json` lo riscrive in JSON e da lì le regole sono queste.

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
# La colonna è un bigint.
_SEQ_MASSIMA = 2**63 - 1


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
    try:
        numero = float(valore)
    except OverflowError as exc:  # un intero JSON di centinaia di cifre
        raise SenmlError(f"{campo} non finito") from exc
    if not math.isfinite(numero):
        raise SenmlError(f"{campo} non finito")
    return numero


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
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        # RecursionError: duemila parentesi annidate stanno in 2 KB.
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
            if not valore.is_integer() or not 0 <= valore <= _SEQ_MASSIMA:
                raise SenmlError("seq deve essere un intero non negativo entro 2**63-1")
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


# RFC 8428 §6, tabella 6: in CBOR le etichette sono interi.
_ETICHETTE_CBOR: dict[int, str] = {
    -1: "bver",
    -2: "bn",
    -3: "bt",
    -4: "bu",
    -5: "bv",
    -6: "bs",
    0: "n",
    1: "u",
    2: "v",
    3: "vs",
    4: "vb",
    5: "s",
    6: "t",
    7: "ut",
    8: "vd",
}


def cbor_a_json(payload: bytes) -> bytes:
    """Un SenML CBOR come SenML JSON, che poi passa da :func:`analizza`.

    Un'etichetta intera fuori dalla tabella non si sa se vada capita per
    forza, e un valore senza equivalente JSON (byte, tag) non è una misura:
    in entrambi i casi si scarta il messaggio.
    """
    import cbor2

    try:
        records = cbor2.loads(payload)
    except (cbor2.CBORError, ValueError, TypeError, RecursionError, OverflowError) as exc:
        # RecursionError: un tag condiviso annida all'infinito, come le
        # parentesi del JSON.
        raise SenmlError("CBOR non valido") from exc
    if not isinstance(records, list):
        raise SenmlError("serve un array SenML non vuoto")
    tradotti: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            raise SenmlError("ogni record deve essere una mappa")
        tradotto: dict[str, Any] = {}
        for chiave, valore in record.items():
            if isinstance(chiave, str):
                nome = chiave
            elif isinstance(chiave, int) and not isinstance(chiave, bool):
                if chiave not in _ETICHETTE_CBOR:
                    raise SenmlError(f"etichetta CBOR {chiave} sconosciuta")
                nome = _ETICHETTE_CBOR[chiave]
            else:
                raise SenmlError("etichetta CBOR né intera né testo")
            tradotto[nome] = valore
        tradotti.append(tradotto)
    try:
        return json.dumps(tradotti, allow_nan=False).encode()
    except (TypeError, ValueError, RecursionError) as exc:
        raise SenmlError("valore CBOR senza equivalente JSON") from exc


__all__ = ["MessaggioV2", "Misura", "SenmlError", "analizza", "cbor_a_json"]
