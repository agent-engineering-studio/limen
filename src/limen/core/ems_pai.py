"""Acqua osservata da Copernicus EMS contro le classi idrauliche del PAI (#713).

Puro: geometrie già in un CRS metrico (EPSG:3035), nessun database. Le
query stanno in :mod:`limen.data.repos.flood_events_repo` e nel loader dei
vettori ISPRA, il report in ``limen ems-confronto-pai``.

L'acqua di un'attivazione è l'**unione** dei prodotti che non sono di
monitoraggio (``DEL0``, ``GRA0``, ``FEP0``): ``DEL1``, ``DEL2`` ridisegnano lo
stesso posto in un giorno diverso, e sommarli conterebbe due volte la stessa
piena. Le classi sono esclusive, vince la più alta: le aree P1 dell'ISPRA
contengono quasi sempre le P2, che contengono le P3, e contare l'acqua in P2
anche dove è in P3 farebbe superare il 100 %.

La quota **fuori** da ogni zona si dà due volte. Grezza, è gonfiata da
strisce sottili lungo i bordi delle zone, dove perimetro EMS e perimetro PAI
non coincidono al metro: la libreria ``copernicus-ems`` le ha misurate,
valgono da 3 a 10 volte il resto. Filtrata, conta solo l'acqua oltre
``tolleranza_m`` da ogni zona, in macchie di almeno ``patch_minima_m2``.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

import shapely
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

#: Le classi idrauliche, dalla più alta: l'ordine è quello in cui vincono.
CLASSI = ("P3", "P2", "P1")

#: Default della misura: quelli con cui la libreria ha preso i numeri di
#: riferimento, così un confronto con lei è a parità di filtro.
TOLLERANZA_M = 50.0
PATCH_MINIMA_M2 = 50_000.0

#: Lato delle tessere in cui si taglia l'acqua. Un'attivazione come EMSR664
#: è un'unica macchia di centinaia di km² con centinaia di migliaia di
#: vertici, e intersecarla intera con ogni pezzo di zona costa minuti.
LATO_TESSERA_M = 2_000.0

_PRODOTTO = re.compile(r"-\d+-\d+$")
_TIPO = re.compile(r"(?P<tipo>[A-Z]+)(?P<numero>\d+)$")


def prodotto(id_poligono: str) -> str:
    """Il prodotto di un poligono di ``flood_events``: ``EMSR664-aoi01-DEL1``."""
    return _PRODOTTO.sub("", id_poligono)


def di_monitoraggio(id_prodotto: str) -> bool:
    """``DEL1``, ``DEL2``… sì; ``DEL0``, ``GRA0``, ``FEP0`` no.

    Un codice che non si legge conta come monitoraggio: meglio perdere un
    prodotto dalla misura che sommare due volte la stessa acqua.
    """
    m = _TIPO.search(id_prodotto)
    return m is None or int(m["numero"]) > 0


@dataclass(frozen=True, slots=True)
class Ripartizione:
    """Metri quadrati di acqua osservata per classe e fuori da ogni zona."""

    acqua_m2: float
    per_classe_m2: dict[str, float]
    fuori_m2: float
    fuori_filtrato_m2: float
    macchie_fuori: int

    def quota(self, m2: float) -> float | None:
        return m2 / self.acqua_m2 if self.acqua_m2 > 0 else None


def _tessere(parti: Sequence[BaseGeometry], lato: float) -> Iterator[BaseGeometry]:
    albero = shapely.STRtree(parti)
    minx, miny, maxx, maxy = shapely.total_bounds(parti)
    x = math.floor(minx / lato) * lato
    while x < maxx:
        y = math.floor(miny / lato) * lato
        while y < maxy:
            riquadro = box(x, y, x + lato, y + lato)
            dentro = [parti[i] for i in albero.query(riquadro, predicate="intersects")]
            if dentro:
                pezzo = shapely.intersection(shapely.union_all(dentro), riquadro)
                if not pezzo.is_empty and pezzo.area > 0:
                    yield pezzo
            y += lato
        x += lato


def _area_dentro(acqua: BaseGeometry, zone: list[BaseGeometry]) -> float:
    if not zone:
        return 0.0
    return float(shapely.intersection(acqua, shapely.union_all(zone)).area)


def ripartisci(
    acqua: Sequence[BaseGeometry],
    zone: Sequence[tuple[str, BaseGeometry]],
    *,
    tolleranza_m: float = TOLLERANZA_M,
    patch_minima_m2: float = PATCH_MINIMA_M2,
    lato_tessera_m: float = LATO_TESSERA_M,
) -> Ripartizione:
    """L'acqua (unione di ``acqua``) divisa fra le classi di ``zone`` e il fuori.

    ``zone`` sono coppie (classe, poligono) già tagliate a pezzi piccoli: il
    mosaico ISPRA ha poligoni da milioni di vertici.
    """
    parti = [
        g
        for g in shapely.get_parts(shapely.make_valid(list(acqua)))
        if g.geom_type in ("Polygon", "MultiPolygon") and g.area > 0
    ]
    vuota = Ripartizione(0.0, dict.fromkeys(CLASSI, 0.0), 0.0, 0.0, 0)
    if not parti:
        return vuota
    classi = [c for c, _ in zone]
    geometrie = [g for _, g in zone]
    albero = shapely.STRtree(geometrie)
    totale = 0.0
    cumulate = dict.fromkeys(CLASSI, 0.0)
    resti: list[BaseGeometry] = []
    for pezzo in _tessere(parti, lato_tessera_m):
        totale += pezzo.area
        vicine = albero.query(pezzo, predicate="dwithin", distance=tolleranza_m)
        for k, classe in enumerate(CLASSI):
            ammesse = CLASSI[: k + 1]
            cumulate[classe] += _area_dentro(
                pezzo, [geometrie[i] for i in vicine if classi[i] in ammesse]
            )
        if len(vicine):
            vicino = shapely.union_all([geometrie[i] for i in vicine])
            pezzo = shapely.difference(pezzo, shapely.buffer(vicino, tolleranza_m))
        if not pezzo.is_empty:
            resti.append(pezzo)
    per_classe: dict[str, float] = {}
    precedente = 0.0
    for classe in CLASSI:
        per_classe[classe] = max(cumulate[classe] - precedente, 0.0)
        precedente = cumulate[classe]
    macchie = [
        m
        for m in shapely.get_parts(shapely.union_all(resti) if resti else shapely.Polygon())
        if m.area >= patch_minima_m2
    ]
    return Ripartizione(
        acqua_m2=totale,
        per_classe_m2=per_classe,
        fuori_m2=max(totale - precedente, 0.0),
        fuori_filtrato_m2=sum(m.area for m in macchie),
        macchie_fuori=len(macchie),
    )


__all__ = [
    "CLASSI",
    "LATO_TESSERA_M",
    "PATCH_MINIMA_M2",
    "TOLLERANZA_M",
    "Ripartizione",
    "di_monitoraggio",
    "prodotto",
    "ripartisci",
]
