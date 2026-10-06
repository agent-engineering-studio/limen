"""Il Bollettino di criticità nazionale/allerta della Protezione Civile.

Pubblicato ogni giorno entro le 16:00 nel repository GitHub del Dipartimento
(`pcm-dpc/DPC-Bollettini-Criticita-Idrogeologica-Idraulica`, CC-BY 4.0), come
GeoJSON per oggi e per domani. È già strutturato: nessun modello linguistico
lo legge, lo si importa.

La lettura degrada a un risultato neutro (``None``) se GitHub non risponde:
il confronto con l'allerta ufficiale è un'informazione in più, non una
condizione per far girare il resto.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from shapely.geometry import MultiPolygon, Polygon, shape

from limen.core.logging import get_logger
from limen.integrations._http import SharedHttpClient, fetch_with_retry

log = get_logger(__name__)

REPO = "pcm-dpc/DPC-Bollettini-Criticita-Idrogeologica-Idraulica"
_API = f"https://api.github.com/repos/{REPO}"
_RAW = f"https://raw.githubusercontent.com/{REPO}/master/files/geojson"
_ROMA = ZoneInfo("Europe/Rome")
#: `20261005_1417_today.json` → emissione del 5 ottobre alle 14:17 (ora italiana).
_NOME = re.compile(r"^(\d{8})_(\d{4})_today\.json$")

#: Dal testo del bollettino al livello: il colore è scritto in chiaro.
_LIVELLI = (("ROSSA", 3), ("ARANCIONE", 2), ("GIALLA", 1))


def livello(testo: str | None) -> int:
    """«Ordinaria per rischio temporali / ALLERTA GIALLA» → 1; nessuna → 0."""
    maiuscolo = (testo or "").upper()
    return next((n for colore, n in _LIVELLI if f"ALLERTA {colore}" in maiuscolo), 0)


@dataclass(frozen=True, slots=True)
class ZonaAllerta:
    valido: date
    zona: str
    livello: int
    idrogeologico: int
    idraulico: int
    temporali: int
    geom: MultiPolygon


@dataclass(frozen=True, slots=True)
class Bollettino:
    nome: str
    emesso: datetime
    zone: list[ZonaAllerta]


def emissione(nome: str) -> datetime | None:
    """L'istante di emissione dal nome del file, in ora italiana."""
    m = _NOME.match(nome)
    if m is None:
        return None
    return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M").replace(tzinfo=_ROMA)


def zone_da_geojson(dati: dict[str, Any], valido: date) -> list[ZonaAllerta]:
    out: list[ZonaAllerta] = []
    for f in dati.get("features") or []:
        p = f.get("properties") or {}
        geom = shape(f["geometry"])
        if isinstance(geom, Polygon):
            geom = MultiPolygon([geom])
        if not isinstance(geom, MultiPolygon) or not p.get("Nome zona"):
            continue
        out.append(
            ZonaAllerta(
                valido=valido,
                zona=str(p["Nome zona"]),
                livello=livello(p.get("Rappresentata nella mappa")),
                idrogeologico=livello(p.get("Per rischio idrogeologico")),
                idraulico=livello(p.get("Per rischio idraulico")),
                temporali=livello(p.get("Per rischio temporali")),
                geom=geom,
            )
        )
    return out


async def _json(url: str) -> Any:
    resp = await fetch_with_retry("GET", url, client=await SharedHttpClient.get())
    return resp.json()


async def ultimo_nome() -> str | None:
    """Il nome dell'ultimo bollettino pubblicato, o ``None``.

    Tre chiamate piccole all'albero del repository invece di una ricorsiva:
    l'archivio ha decine di migliaia di file.
    """
    try:
        radice = await _json(f"{_API}/git/trees/master")
        files = next(t["sha"] for t in radice["tree"] if t["path"] == "files")
        sotto = await _json(f"{_API}/git/trees/{files}")
        geojson = next(t["sha"] for t in sotto["tree"] if t["path"] == "geojson")
        elenco = await _json(f"{_API}/git/trees/{geojson}")
    except (httpx.HTTPError, KeyError, StopIteration, ValueError) as exc:
        log.warning("integration.degraded", source="dpc_bollettini", error=str(exc))
        return None
    nomi = sorted(t["path"] for t in elenco.get("tree", []) if _NOME.match(t["path"]))
    return nomi[-1] if nomi else None


async def scarica(nome: str) -> Bollettino | None:
    """Oggi e domani del bollettino ``nome``, o ``None`` se non si legge."""
    emesso = emissione(nome)
    if emesso is None:
        return None
    radice = nome.removesuffix("_today.json")
    giorno = emesso.date()
    try:
        oggi = await _json(f"{_RAW}/{radice}_today.json")
        domani = await _json(f"{_RAW}/{radice}_tomorrow.json")
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("integration.degraded", source="dpc_bollettini", file=nome, error=str(exc))
        return None
    zone = zone_da_geojson(oggi, giorno) + zone_da_geojson(domani, giorno + timedelta(days=1))
    return Bollettino(nome=radice, emesso=emesso, zone=zone)
