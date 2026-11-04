"""La PGA di una ShakeMap INGV sulle celle di Limen (#284).

Il parser è quello del pacchetto ``ingv-shakemap``: ordine delle righe
controllato, PGA in percento di g convertita in g. Qui resta quello che vuole
Limen: una griglia senza PGA in g è illeggibile (non c'è altro da cui ricavare
lo scuotimento), e il conto per cella, lo stesso nel job e nel backtest.

È lo scuotimento che INGV stima con le stazioni e le sue leggi di
attenuazione: Limen non ne inventa una sua.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from ingv_shakemap import GridError, ShakeGrid, parse_grid
from ingv_shakemap.grid import PERCENT_G


class GrigliaNonValidaError(ValueError):
    """Il file non è una griglia ShakeMap leggibile."""


def leggi_griglia(xml: bytes) -> ShakeGrid:
    """Solleva solo :class:`GrigliaNonValidaError`: una griglia storta non deve
    fermare la sincronizzazione degli altri eventi."""
    try:
        griglia = parse_grid(xml)
    except GridError as exc:
        raise GrigliaNonValidaError(str(exc)) from exc
    pga = griglia.fields.get("PGA")
    if pga is None:
        raise GrigliaNonValidaError("manca la colonna PGA")
    if pga.units not in PERCENT_G | {"g"}:
        raise GrigliaNonValidaError(f"PGA in {pga.units!r}, attesa in percento di g o in g")
    return griglia


def celle_scosse[K](
    griglia: ShakeGrid,
    celle: Sequence[tuple[K, float, float]],
    pga_min_g: float,
) -> list[tuple[K, float]]:
    """``(chiave, PGA in g)`` delle celle scosse almeno ``pga_min_g``.

    ``celle`` sono ``(chiave, lon, lat)`` del centroide; vale il punto di
    griglia più vicino, e una cella fuori dalla griglia non è scossa. Una
    chiamata NumPy per tutte: su 100.000 punti 10 ms, contro 280 del ciclo.
    """
    if not celle:
        return []
    lons = np.fromiter((c[1] for c in celle), dtype=float, count=len(celle))
    lats = np.fromiter((c[2] for c in celle), dtype=float, count=len(celle))
    pga = griglia.sample_g("PGA", lons, lats)
    # NaN fuori dalla griglia: il confronto è falso, la cella non entra.
    scosse = np.flatnonzero(pga >= pga_min_g)
    return [(celle[int(i)][0], float(pga[i])) for i in scosse]


__all__ = ["GrigliaNonValidaError", "celle_scosse", "leggi_griglia"]
