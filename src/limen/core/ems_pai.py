"""Acqua osservata da Copernicus EMS contro le classi idrauliche del PAI (#713).

Puro: geometrie già in un CRS metrico (EPSG:3035), nessun database. Il conto è
di ``copernicus-ems`` (``overlay.split_by_zones``, ``ids``); qui restano i nomi
italiani e le classi del PAI. Le
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

from collections.abc import Sequence
from dataclasses import dataclass

from copernicus_ems.ids import is_monitoring, polygon_product_id
from copernicus_ems.overlay import MIN_PATCH_M2, TILE_M, TOLERANCE_M, split_by_zones
from shapely.geometry.base import BaseGeometry

#: Le classi idrauliche, dalla più alta: l'ordine è quello in cui vincono.
CLASSI = ("P3", "P2", "P1")
#: Default della misura: quelli di copernicus-ems, così un confronto con lei è
#: a parità di filtro.
TOLLERANZA_M = TOLERANCE_M
PATCH_MINIMA_M2 = MIN_PATCH_M2
#: Lato delle tessere in cui si taglia l'acqua.
LATO_TESSERA_M = TILE_M


def prodotto(id_poligono: str) -> str:
    """Il prodotto di un poligono di ``flood_events``: ``EMSR664-aoi01-DEL1``."""
    return polygon_product_id(id_poligono)


def di_monitoraggio(id_prodotto: str) -> bool:
    """``DEL1``, ``DEL2``… sì; ``DEL0``, ``GRA0``, ``FEP0`` no; un codice illeggibile sì."""
    return is_monitoring(id_prodotto)


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


def ripartisci(
    acqua: Sequence[BaseGeometry],
    zone: Sequence[tuple[str, BaseGeometry]],
    *,
    tolleranza_m: float = TOLLERANZA_M,
    patch_minima_m2: float = PATCH_MINIMA_M2,
    lato_tessera_m: float = LATO_TESSERA_M,
) -> Ripartizione:
    """L'acqua (unione di ``acqua``) divisa fra le classi di ``zone`` e il fuori.

    ``copernicus_ems.overlay.split_by_zones`` con le classi del PAI.
    """
    found = split_by_zones(
        acqua,
        zone,
        classes=CLASSI,
        tolerance_m=tolleranza_m,
        min_patch_m2=patch_minima_m2,
        tile_m=lato_tessera_m,
    )
    return Ripartizione(
        acqua_m2=found.water_m2,
        per_classe_m2=dict(found.by_class_m2),
        fuori_m2=found.outside_m2,
        fuori_filtrato_m2=found.outside_filtered_m2,
        macchie_fuori=found.outside_patches,
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
