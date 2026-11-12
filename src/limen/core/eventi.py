"""Limen come sorgente di eventi MCP (#371): il catalogo, i cursori, i payload.

Estensione sperimentale ``io.modelcontextprotocol/events`` (bozza «design
sketch» del gruppo di lavoro), solo nella modalità **poll**: nessuno stato
per client, nessun webhook, niente da ricordare fra una richiesta e l'altra.
Un agente esterno chiede «che cosa è successo dopo il mio cursore» e combina
la risposta con fonti che Limen non ha.

Quattro eventi, tutti letti da tabelle che già esistono e scritte dai
percorsi orario e previsionale, che qui non si toccano:

* ``limen.alert.dispatched`` — un'allerta di Limen davvero spedita
  (``alert_dispatches``, già deduplicata);
* ``limen.risk.class_changed`` — una cella cambia classe nello sweep orario;
* ``limen.source.unmeasured`` — una cella passa a «non misurato»: mancava il
  dato, non è quiete. È l'invariante di Limen portato fuori: un agente deve
  poter distinguere «calmo» da «non lo so»;
* ``limen.forecast.escalated`` — una corsa previsionale (+24/+48/+72 h) porta
  una cella ad almeno ``min_level`` dove la corsa precedente la teneva sotto.
  Lo storico previsionale tiene solo le celle da Moderato in su, quindi
  «nessuna riga» nella corsa precedente vuol dire «sotto Moderato» — ma solo
  se quella corsa c'è stata: senza, non si scrive niente.

Ogni payload dice che è una stima di Limen e non un'allerta ufficiale, e quelli
dell'alluvione portano l'attribuzione Copernicus richiesta dalla licenza CEMS.

Puro: le query stanno in ``data/repos/eventi_repo.py``, il protocollo in
``mcp/eventi.py``.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from limen.core.models.hazard import HazardType
from limen.core.models.risk import RiskLevel

IDENTIFICATORE = "io.modelcontextprotocol/events"

ALLERTA = "limen.alert.dispatched"
CAMBIO_CLASSE = "limen.risk.class_changed"
NON_MISURATO = "limen.source.unmeasured"
PREVISIONE = "limen.forecast.escalated"

#: Errori della bozza (SEP-3415, provvisori finché non è accettata).
NON_TROVATO = -32023
PARAMETRI_NON_VALIDI = -32602

AVVERTENZA = (
    "Stima automatica di Limen, non un'allerta ufficiale: le allerte sono "
    "quelle della Protezione Civile."
)

_ORDINE = [lv.value for lv in RiskLevel]


def attribuzione(hazard: str, anno: int) -> str | None:
    """La formula della licenza CEMS per i dati derivati da GloFAS (alluvione)."""
    if hazard != HazardType.FLOOD.value:
        return None
    return f"Contains modified Copernicus Emergency Management Service information, {anno}"


class ArgomentiNonValidiError(ValueError):
    """Argomenti che non rispettano l'``inputSchema`` dell'evento."""


@dataclass(frozen=True, slots=True)
class Filtro:
    hazard: str | None
    aoi_id: str | None
    livello_minimo: str | None


_LIVELLO = {"type": "string", "enum": _ORDINE[1:]}
_COMUNI: dict[str, Any] = {
    "hazard": {"type": "string", "enum": [h.value for h in HazardType]},
    "aoi_id": {"type": "string", "description": "Regione, es. it-puglia. Vuoto: tutta Italia."},
}
_COMUNE_PAYLOAD: dict[str, Any] = {
    "cell_id": {"type": "string"},
    "aoi_id": {"type": "string"},
    "hazard": {"type": "string"},
    "avvertenza": {"type": "string"},
    "attribuzione": {"type": ["string", "null"]},
}


def catalogo() -> list[dict[str, Any]]:
    """La risposta di ``events/list``: nome, descrizione, schemi, modalità."""
    return [
        {
            "name": ALLERTA,
            "description": (
                "Un'allerta di Limen spedita sui canali configurati, già deduplicata. "
                "Non è un'allerta della Protezione Civile."
            ),
            "delivery": ["poll"],
            "inputSchema": {
                "type": "object",
                "properties": {**_COMUNI, "min_level": {**_LIVELLO, "default": "Moderate"}},
            },
            "payloadSchema": {
                "type": "object",
                "properties": {
                    **_COMUNE_PAYLOAD,
                    "level": {"type": "string"},
                    "score": {"type": "number"},
                    "summary": {"type": ["string", "null"]},
                },
            },
        },
        {
            "name": CAMBIO_CLASSE,
            "description": (
                "Una cella da 1 km cambia classe nello sweep orario, salendo o scendendo, "
                "quando una delle due classi è almeno min_level."
            ),
            "delivery": ["poll"],
            "inputSchema": {
                "type": "object",
                "properties": {**_COMUNI, "min_level": {**_LIVELLO, "default": "High"}},
            },
            "payloadSchema": {
                "type": "object",
                "properties": {
                    **_COMUNE_PAYLOAD,
                    "from": {"type": ["string", "null"]},
                    "to": {"type": "string"},
                    "score": {"type": "number"},
                    "measured": {"type": ["boolean", "null"]},
                },
            },
        },
        {
            "name": NON_MISURATO,
            "description": (
                "Una cella passa a «non misurato»: il dato meteo non è arrivato. "
                "Il punteggio basso che l'accompagna non vuol dire quiete."
            ),
            "delivery": ["poll"],
            "inputSchema": {"type": "object", "properties": dict(_COMUNI)},
            "payloadSchema": {"type": "object", "properties": dict(_COMUNE_PAYLOAD)},
        },
        {
            "name": PREVISIONE,
            "description": (
                "Una corsa previsionale porta una cella da 1 km ad almeno min_level fra "
                "24, 48 o 72 ore, dove la corsa precedente la teneva sotto. from null vuol "
                "dire sotto Moderato. Non è un'allerta: è una previsione che sale."
            ),
            "delivery": ["poll"],
            "inputSchema": {
                "type": "object",
                "properties": {**_COMUNI, "min_level": {**_LIVELLO, "default": "High"}},
            },
            "payloadSchema": {
                "type": "object",
                "properties": {
                    **_COMUNE_PAYLOAD,
                    "from": {"type": ["string", "null"]},
                    "to": {"type": "string"},
                    "score": {"type": "number"},
                    "horizon_hours": {"type": "integer"},
                    "target_at": {"type": "string", "format": "date-time"},
                },
            },
        },
    ]


NOMI = frozenset(e["name"] for e in catalogo())


def filtro(nome: str, argomenti: Mapping[str, Any] | None) -> Filtro:
    """Gli argomenti validati contro l'``inputSchema``; :class:`ArgomentiNonValidiError` se no."""
    arg = dict(argomenti or {})
    ammessi = {"hazard", "aoi_id"} | ({"min_level"} if nome != NON_MISURATO else set())
    estranei = sorted(set(arg) - ammessi)
    if estranei:
        raise ArgomentiNonValidiError(f"argomenti sconosciuti: {', '.join(estranei)}")
    hazard = arg.get("hazard")
    if hazard is not None and hazard not in {h.value for h in HazardType}:
        raise ArgomentiNonValidiError(f"hazard non valido: {hazard!r}")
    aoi = arg.get("aoi_id")
    if aoi is not None and not isinstance(aoi, str):
        raise ArgomentiNonValidiError("aoi_id dev'essere una stringa")
    livello: str | None = None
    if nome != NON_MISURATO:
        livello = arg.get("min_level", "Moderate" if nome == ALLERTA else "High")
        if livello not in _ORDINE[1:]:
            raise ArgomentiNonValidiError(f"min_level non valido: {livello!r}")
    return Filtro(hazard=hazard, aoi_id=aoi, livello_minimo=livello)


def livelli_da(minimo: str) -> list[str]:
    """Le classi da ``minimo`` in su, nell'ordine della scala."""
    return _ORDINE[_ORDINE.index(minimo) :]


@dataclass(frozen=True, slots=True)
class Posizione:
    """Dove è arrivato un abbonato: un istante e un id per spezzare i pari."""

    t: datetime | None
    id: int


def codifica(p: Posizione) -> str:
    corpo = {"id": p.id, **({"t": p.t.isoformat()} if p.t is not None else {})}
    return base64.urlsafe_b64encode(json.dumps(corpo).encode()).decode().rstrip("=")


def decodifica(cursore: str) -> Posizione:
    """Il cursore opaco; :class:`ArgomentiNonValidiError` se non è uno dei nostri."""
    try:
        grezzo = base64.urlsafe_b64decode(cursore + "=" * (-len(cursore) % 4))
        corpo = json.loads(grezzo)
        t = datetime.fromisoformat(corpo["t"]) if "t" in corpo else None
        return Posizione(t=t, id=int(corpo["id"]))
    except (ValueError, KeyError, TypeError) as exc:
        raise ArgomentiNonValidiError("cursore non valido") from exc


def payload(riga: Mapping[str, Any], nome: str, anno: int) -> dict[str, Any]:
    """Il ``data`` di un evento, dalla riga letta dal repository."""
    hazard = str(riga["hazard"])
    base = {
        "cell_id": riga["cell_id"],
        "aoi_id": riga["aoi_id"],
        "hazard": hazard,
        "avvertenza": AVVERTENZA,
        "attribuzione": attribuzione(hazard, anno),
    }
    if nome == ALLERTA:
        return {
            **base,
            "level": riga["level"],
            "score": float(riga["score"]),
            "summary": riga["summary"],
        }
    if nome == CAMBIO_CLASSE:
        return {
            **base,
            "from": riga["prima"],
            "to": riga["classe"],
            "score": float(riga["score"]),
            "measured": riga["measured"],
        }
    if nome == PREVISIONE:
        ore = int(str(riga["horizon"]).strip("+h"))
        return {
            **base,
            "from": riga["prima"],
            "to": riga["classe"],
            "score": float(riga["score"]),
            "horizon_hours": ore,
            "target_at": (riga["t"] + timedelta(hours=ore)).astimezone(UTC).isoformat(),
        }
    return base


def id_evento(nome: str, riga: Mapping[str, Any]) -> str:
    """Stabile: la stessa riga dà sempre lo stesso id, per la deduplica del client."""
    prefisso = {
        ALLERTA: "alert",
        CAMBIO_CLASSE: "class",
        NON_MISURATO: "unmeasured",
        PREVISIONE: "forecast",
    }[nome]
    return f"{prefisso}:{riga['id']}"


__all__ = [
    "ALLERTA",
    "AVVERTENZA",
    "CAMBIO_CLASSE",
    "IDENTIFICATORE",
    "NOMI",
    "NON_MISURATO",
    "NON_TROVATO",
    "PARAMETRI_NON_VALIDI",
    "PREVISIONE",
    "ArgomentiNonValidiError",
    "Filtro",
    "Posizione",
    "attribuzione",
    "catalogo",
    "codifica",
    "decodifica",
    "filtro",
    "id_evento",
    "livelli_da",
    "payload",
]
