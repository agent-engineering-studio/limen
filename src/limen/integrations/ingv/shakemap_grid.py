"""La PGA di una ShakeMap INGV sulle celle di Limen (#284).

Tutto il conto è di ``ingv-shakemap``: la lettura della griglia (ordine delle
righe controllato, PGA in percento di g convertita in g), il controllo che la
PGA ci sia e sia in g (``ShakeGrid.require_g``) e le celle scosse oltre una
soglia (``shaken_points``, il punto di griglia più vicino). Qui resta solo
l'errore di Limen: una griglia storta non deve fermare la sincronizzazione
degli altri eventi.

È lo scuotimento che INGV stima con le stazioni e le sue leggi di
attenuazione: Limen non ne inventa una sua.
"""

from __future__ import annotations

from collections.abc import Sequence

from ingv_shakemap import GridError, ShakeGrid, parse_grid, shaken_points


class GrigliaNonValidaError(ValueError):
    """Il file non è una griglia ShakeMap leggibile."""


def leggi_griglia(xml: bytes) -> ShakeGrid:
    """La griglia, con la PGA in g; solleva solo :class:`GrigliaNonValidaError`."""
    try:
        griglia = parse_grid(xml)
        griglia.require_g("PGA")
    except GridError as exc:
        raise GrigliaNonValidaError(str(exc)) from exc
    return griglia


def celle_scosse[K](
    griglia: ShakeGrid,
    celle: Sequence[tuple[K, float, float]],
    pga_min_g: float,
) -> list[tuple[K, float]]:
    """``(chiave, PGA in g)`` delle celle scosse almeno ``pga_min_g``.

    È ``ingv_shakemap.shaken_points``: il punto di griglia più vicino, e una
    cella fuori dalla griglia non è scossa.
    """
    return shaken_points(griglia, celle, pga_min_g)


__all__ = ["GrigliaNonValidaError", "celle_scosse", "leggi_griglia"]
