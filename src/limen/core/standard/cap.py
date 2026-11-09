"""CAP 1.2 per i comuni in allerta (#499).

Un messaggio per (comune, pericolo) in classe Alta o Molto alta, costruito dalla
riga di ``mv_comune_risk``: niente LLM, niente numeri che la riga non abbia
(«Alerts never invent figures»). L'area è il comune, con il codice ISTAT come
``geocode``: un poligono comunale pesa decine di kB, e chi riceve un CAP
italiano ha già i confini ISTAT.

Il fuso è quello di Roma: CAP vieta «Z» e vuole UTC scritto ``-00:00``, una
forma che molte librerie non producono; l'ora locale con il suo scarto è
inequivocabile ed è quella che legge un operatore italiano.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import cache
from importlib import resources
from typing import Any, Literal
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, ConfigDict, Field

from limen.core.models.hazard import HazardType

NS = "urn:oasis:names:tc:emergency:cap:1.2"
MEDIA_TYPE = "application/cap+xml"
_ROMA = ZoneInfo("Europe/Rome")
_CLASSE_IT = {"High": "Alta", "VeryHigh": "Molto alta"}


class _Rigido(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _Classe(_Rigido):
    urgency: Literal["Immediate", "Expected", "Future", "Past", "Unknown"]
    severity: Literal["Extreme", "Severe", "Moderate", "Minor", "Unknown"]
    certainty: Literal["Observed", "Likely", "Possible", "Unlikely", "Unknown"]


class _Pericolo(_Rigido):
    category: Literal[
        "Geo", "Met", "Safety", "Security", "Rescue", "Fire", "Health", "Env", "Transport", "Infra"
    ]
    event: str = Field(min_length=1)


class ConfigCap(_Rigido):
    sender: str = Field(pattern=r"^[^\s,<&]+$")
    sender_name: str
    #: `Actual` non è fra i valori ammessi: un messaggio di Limen non può
    #: presentarsi come un avviso reale, qualunque cosa dica il file.
    status: Literal["Exercise", "Test", "System"]
    validita_ore: int = Field(gt=0)
    nota: str
    classi: dict[str, _Classe]
    pericoli: dict[HazardType, _Pericolo]


@cache
def carica_config() -> ConfigCap:
    testo = resources.files("limen.config").joinpath("cap.yaml").read_text(encoding="utf-8")
    return ConfigCap.model_validate(yaml.safe_load(testo))


@dataclass(frozen=True, slots=True)
class ComuneInAllerta:
    """La riga di ``mv_comune_risk`` che il messaggio racconta."""

    istat_code: str
    name: str
    hazard: HazardType
    worst_class: str
    max_score: float
    n_cells: int
    n_alert: int
    computed_at: datetime


def attribuzione_copernicus(anno: int) -> str:
    return (
        f"Contiene informazioni modificate del Copernicus Emergency Management Service, {anno}. "
        "Non è un avviso di piena."
    )


def identificativo(c: ComuneInAllerta) -> str:
    """Stabile per lo stesso calcolo: cambia quando cambia ``computed_at``."""
    istante = c.computed_at.astimezone(_ROMA).strftime("%Y%m%dT%H%M%S")
    return f"limen-{c.hazard.value}-{c.istat_code}-{istante}"


def da_identificativo(ident: str) -> tuple[HazardType, str, str] | None:
    """``(pericolo, istat, istante)`` da un identificativo, o ``None``."""
    parti = ident.split("-")
    if len(parti) != 4 or parti[0] != "limen":
        return None
    try:
        hazard = HazardType(parti[1])
    except ValueError:
        return None
    return hazard, parti[2], parti[3]


def _ora(t: datetime) -> str:
    return t.astimezone(_ROMA).replace(microsecond=0).isoformat()


def _figlio(padre: ET.Element, nome: str, testo: str) -> ET.Element:
    el = ET.SubElement(padre, f"{{{NS}}}{nome}")
    el.text = testo
    return el


def descrizione(c: ComuneInAllerta, cfg: ConfigCap) -> str:
    classe = _CLASSE_IT.get(c.worst_class, c.worst_class)
    testo = (
        f"{cfg.pericoli[c.hazard].event}: classe {classe} su {c.name}. "
        f"{c.n_alert} celle da 1 km² su {c.n_cells} sono in classe Alta o Molto alta; "
        f"punteggio massimo {c.max_score:.2f} su 1. Calcolo delle {_ora(c.computed_at)}."
    )
    if c.hazard is HazardType.FLOOD:
        testo += " " + attribuzione_copernicus(c.computed_at.year)
    return testo


def messaggio(c: ComuneInAllerta, cfg: ConfigCap | None = None) -> bytes:
    """Il messaggio CAP 1.2 del comune, in UTF-8."""
    cfg = cfg or carica_config()
    classe = cfg.classi[c.worst_class]
    pericolo = cfg.pericoli[c.hazard]
    ET.register_namespace("", NS)
    alert = ET.Element(f"{{{NS}}}alert")
    _figlio(alert, "identifier", identificativo(c))
    _figlio(alert, "sender", cfg.sender)
    _figlio(alert, "sent", _ora(c.computed_at))
    _figlio(alert, "status", cfg.status)
    _figlio(alert, "msgType", "Alert")
    _figlio(alert, "scope", "Public")
    _figlio(alert, "note", " ".join(cfg.nota.split()))
    info = ET.SubElement(alert, f"{{{NS}}}info")
    _figlio(info, "language", "it-IT")
    _figlio(info, "category", pericolo.category)
    _figlio(info, "event", pericolo.event)
    _figlio(info, "urgency", classe.urgency)
    _figlio(info, "severity", classe.severity)
    _figlio(info, "certainty", classe.certainty)
    _figlio(info, "effective", _ora(c.computed_at))
    _figlio(info, "expires", _ora(c.computed_at + timedelta(hours=cfg.validita_ore)))
    _figlio(info, "senderName", cfg.sender_name)
    _figlio(info, "headline", f"{pericolo.event}: {c.name}")
    _figlio(info, "description", descrizione(c, cfg))
    area = ET.SubElement(info, f"{{{NS}}}area")
    _figlio(area, "areaDesc", c.name)
    geocode = ET.SubElement(area, f"{{{NS}}}geocode")
    _figlio(geocode, "valueName", "ISTAT")
    _figlio(geocode, "value", c.istat_code)
    return bytes(ET.tostring(alert, encoding="utf-8", xml_declaration=True))


def feed_atom(
    comuni: list[ComuneInAllerta],
    *,
    base_url: str,
    aggiornato: datetime,
    cfg: ConfigCap | None = None,
) -> bytes:
    """Il feed Atom dei messaggi: un ``entry`` per comune, con il link al CAP."""
    cfg = cfg or carica_config()
    atom = "http://www.w3.org/2005/Atom"
    ET.register_namespace("", atom)
    feed = ET.Element(f"{{{atom}}}feed")

    def f(padre: ET.Element, nome: str, testo: str | None = None, **attr: Any) -> ET.Element:
        el = ET.SubElement(padre, f"{{{atom}}}{nome}", {k: str(v) for k, v in attr.items()})
        if testo is not None:
            el.text = testo
        return el

    base = base_url.rstrip("/")
    f(feed, "id", f"{base}/api/cap")
    f(feed, "title", "Limen — comuni in classe Alta o Molto alta (CAP 1.2, non ufficiale)")
    f(feed, "updated", _ora(aggiornato))
    f(feed, "link", rel="self", href=f"{base}/api/cap")
    autore = f(feed, "author")
    f(autore, "name", "Limen")
    for c in comuni:
        ident = identificativo(c)
        e = f(feed, "entry")
        f(e, "id", f"urn:limen:cap:{ident}")
        f(e, "title", f"{cfg.pericoli[c.hazard].event}: {c.name}")
        f(e, "updated", _ora(c.computed_at))
        f(e, "summary", descrizione(c, cfg))
        f(e, "link", rel="alternate", type=MEDIA_TYPE, href=f"{base}/api/cap/{ident}")
    return bytes(ET.tostring(feed, encoding="utf-8", xml_declaration=True))
