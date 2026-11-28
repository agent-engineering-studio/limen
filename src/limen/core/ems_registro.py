"""Registro di un'attivazione Copernicus EMS per comune (#713).

Per ogni attivazione alluvionale già in ``flood_events``: i comuni ISTAT
toccati dall'acqua osservata, i km² per comune (EPSG:3035), quando è
cominciato l'evento, quando è stato osservato, da quali prodotti EMS.

L'acqua è la stessa di ``limen ems-confronto-pai``: l'unione dei prodotti
che non sono di monitoraggio, così un comune ridisegnato tre volte non ha il
triplo dell'acqua. È acqua **osservata dopo**, da satellite: un limite
inferiore di ciò che è successo, mai un'allerta né una previsione. Ogni
uscita porta l'attribuzione che la licenza CEMS chiede.

Le query stanno in :mod:`limen.data.repos.flood_events_repo`; qui la parte
pura (km² per comune, CSV, JSON) e l'orchestrazione per l'endpoint.
"""

from __future__ import annotations

import asyncio
import csv
import io
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from copernicus_ems import attribution
from copernicus_ems.overlay import WaterPolygon, places_hit
from shapely.geometry.base import BaseGeometry

from limen.core.ems_pai import di_monitoraggio, prodotto
from limen.data.repos import flood_events_repo

AVVERTENZA = (
    "Acqua osservata da satellite dopo l'evento (Copernicus EMS Rapid Mapping): un limite "
    "inferiore di ciò che è stato allagato, non un'allerta né una previsione."
)

COLONNE = (
    "attivazione",
    "istat_code",
    "comune",
    "aoi_id",
    "acqua_km2",
    "inizio_evento",
    "osservato_dal",
    "osservato_al",
    "prodotti",
    "attribuzione",
)


def attribuzione(anno: int) -> str:
    """La formula della licenza CEMS, con l'anno del dato: ``copernicus_ems.attribution``."""
    return attribution(anno)


@dataclass(frozen=True, slots=True)
class Poligono:
    """Un poligono di acqua osservata, in un CRS metrico."""

    prodotto: str
    geom: BaseGeometry
    inizio: datetime
    osservato: datetime | None


@dataclass(frozen=True, slots=True)
class Comune:
    istat_code: str
    nome: str
    aoi_id: str
    geom: BaseGeometry


@dataclass(frozen=True, slots=True)
class ComuneColpito:
    istat_code: str
    nome: str
    aoi_id: str
    acqua_km2: float
    inizio: datetime
    osservato_dal: datetime | None
    osservato_al: datetime | None
    prodotti: tuple[str, ...]


def comuni_colpiti(acqua: Sequence[Poligono], comuni: Sequence[Comune]) -> list[ComuneColpito]:
    """Un record per comune toccato dall'acqua, dal più allagato: ``copernicus_ems.places_hit``.

    Per comune si fa l'**unione** dei pezzi d'acqua, non la somma; un comune
    toccato solo sul confine non conta.
    """
    if not acqua or not comuni:
        return []
    colpiti = places_hit(
        [WaterPolygon(p.prodotto, p.geom, p.inizio, p.osservato) for p in acqua],
        [(str(i), c.geom) for i, c in enumerate(comuni)],
    )
    out = [
        ComuneColpito(
            istat_code=comuni[int(h.key)].istat_code,
            nome=comuni[int(h.key)].nome,
            aoi_id=comuni[int(h.key)].aoi_id,
            acqua_km2=h.water_km2,
            inizio=h.start,
            osservato_dal=h.observed_from,
            osservato_al=h.observed_to,
            prodotti=h.products,
        )
        for h in colpiti
    ]
    return sorted(out, key=lambda r: (-r.acqua_km2, r.istat_code))


def _ora(t: datetime | None) -> str:
    return "" if t is None else t.isoformat()


def _riga(codice: str, r: ComuneColpito) -> dict[str, Any]:
    return {
        "attivazione": codice,
        "istat_code": r.istat_code,
        "comune": r.nome,
        "aoi_id": r.aoi_id,
        "acqua_km2": round(r.acqua_km2, 4),
        "inizio_evento": _ora(r.inizio),
        "osservato_dal": _ora(r.osservato_dal),
        "osservato_al": _ora(r.osservato_al),
        "prodotti": " ".join(r.prodotti),
        "attribuzione": attribuzione(r.inizio.year),
    }


def registro_csv(codice: str, righe: Sequence[ComuneColpito]) -> str:
    """Il registro in CSV. L'attribuzione è una colonna: viaggia con ogni riga."""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLONNE, lineterminator="\n")
    w.writeheader()
    for r in righe:
        w.writerow(_riga(codice, r))
    return buf.getvalue()


def registro_json(
    codice: str, righe: Sequence[ComuneColpito], *, nome: str | None = None
) -> dict[str, Any]:
    anni = sorted({r.inizio.year for r in righe})
    return {
        "attivazione": codice,
        "nome": nome,
        "avvertenza": AVVERTENZA,
        "attribuzione": attribuzione(anni[0]) if anni else None,
        "acqua_km2": round(sum(r.acqua_km2 for r in righe), 4),
        "comuni": [
            {k: v for k, v in _riga(codice, r).items() if k != "attivazione"} for r in righe
        ],
    }


#: Il registro di EMSR664 costa quasi un minuto (28 MB di poligoni e
#: l'intersezione con 35 comuni), e il catalogo cambia solo con
#: ``limen ingest-events``: si tiene in memoria qualche ora.
_DURATA_S = 6 * 3600.0
_memoria: dict[str, tuple[float, list[ComuneColpito]]] = {}


#: Un calcolo per attivazione alla volta: dieci richieste insieme sul
#: registro di EMSR664 sarebbero dieci minuti di CPU sul processo della mappa.
_in_corso: dict[str, asyncio.Lock] = {}


async def registro(codice: str) -> list[ComuneColpito] | None:
    """I comuni toccati da ``codice``; ``None`` se l'attivazione non c'è."""
    async with _in_corso.setdefault(codice, asyncio.Lock()):
        tenuto = _memoria.get(codice)
        if tenuto is not None and time.monotonic() - tenuto[0] < _DURATA_S:
            return tenuto[1]
        righe_comuni = await _calcola(codice)
        # Solo le attivazioni che ci sono: un codice inventato non occupa memoria.
        if righe_comuni is not None:
            _memoria[codice] = (time.monotonic(), righe_comuni)
        else:
            _in_corso.pop(codice, None)
        return righe_comuni


async def _calcola(codice: str) -> list[ComuneColpito] | None:
    righe = await flood_events_repo.acqua_osservata(codice)
    if not righe:
        return None
    acqua = [
        Poligono(
            prodotto=prodotto(r.id), geom=r.geom, inizio=r.event_time, osservato=r.observed_time
        )
        for r in righe
        if not di_monitoraggio(prodotto(r.id))
    ]
    comuni = [
        Comune(istat_code=c.istat_code, nome=c.nome, aoi_id=c.aoi_id, geom=c.geom)
        for c in await flood_events_repo.comuni_nel_riquadro(codice)
    ]
    # In un thread: su EMSR664 sono secondi di shapely, e il loop serve la mappa.
    return await asyncio.to_thread(comuni_colpiti, acqua, comuni)


async def attivazioni() -> list[dict[str, Any]]:
    """Le attivazioni in catalogo, ciascuna con la sua attribuzione."""
    return [
        {
            "attivazione": a.activation_code,
            "nome": a.name,
            "inizio_evento": a.event_time.isoformat(),
            "poligoni": a.polygons,
            "attribuzione": attribuzione(a.event_time.year),
        }
        for a in await flood_events_repo.activations_summary()
    ]


__all__ = [
    "AVVERTENZA",
    "COLONNE",
    "Comune",
    "ComuneColpito",
    "Poligono",
    "attivazioni",
    "attribuzione",
    "comuni_colpiti",
    "registro",
    "registro_csv",
    "registro_json",
]
