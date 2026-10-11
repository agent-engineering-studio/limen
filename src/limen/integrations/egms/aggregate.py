"""Dalla griglia EGMS a 100 m alle celle da 1 km di Limen.

Le celle sono quadrati da 1 km in EPSG:3035 con un'origine per AOI, quindi
non allineati ai pixel da 100 m delle tile: una cella prende i pixel il cui
**centro** cade dentro di lei, di norma 10 x 10. Per cella:

* ``velocita_verticale_mmy`` / ``velocita_est_mmy`` — la mediana di ciascuna
  componente, con segno (su/giù, est/ovest);
* ``insar_velocity_mmy`` — il 90° percentile del modulo ``sqrt(E² + U²)``:
  una frana occupa pochi pixel di una cella da 1 km, e la mediana la
  cancellerebbe;
* ``scatterer_count`` — i pixel con entrambe le componenti valide. Zero vuol
  dire «il satellite qui non vede» (bosco, ombra radar), non «terreno fermo».
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from limen.data.repos.cell_insar_features_repo import CellInsarFeatures

PASSO_M = 100.0
_NODATA = -9999.0


@dataclass(frozen=True, slots=True)
class Cella:
    """Una cella con i suoi limiti in EPSG:3035."""

    cell_id: str
    minx: float
    miny: float
    maxx: float
    maxy: float


@dataclass(frozen=True, slots=True)
class Griglia:
    """Le due componenti sulla stessa griglia: ``top``/``left`` dell'angolo
    in alto a sinistra, NaN dove il dato manca."""

    verticale: Any
    est: Any
    left: float
    top: float


def mosaico(tiff: list[Path], *, minx: float, miny: float, maxx: float, maxy: float) -> Any:
    """Le tile di una componente cucite sul rettangolo, NaN dove mancano.

    I limiti si allargano ai multipli di 100 m: le tile EGMS stanno su quella
    griglia, e un ricampionamento sposterebbe i pixel.
    """
    import rasterio
    from rasterio.merge import merge

    x0 = math.floor(minx / PASSO_M) * PASSO_M
    y0 = math.floor(miny / PASSO_M) * PASSO_M
    x1 = math.ceil(maxx / PASSO_M) * PASSO_M
    y1 = math.ceil(maxy / PASSO_M) * PASSO_M
    righe = round((y1 - y0) / PASSO_M)
    colonne = round((x1 - x0) / PASSO_M)
    if not tiff:
        return np.full((righe, colonne), np.nan, dtype="float32")
    aperti = [rasterio.open(p) for p in tiff]
    try:
        dati, _ = merge(aperti, bounds=(x0, y0, x1, y1), res=PASSO_M, nodata=_NODATA)
    finally:
        for r in aperti:
            r.close()
    banda = dati[0].astype("float32")
    banda[banda == _NODATA] = np.nan
    return banda


def per_cella(celle: list[Cella], griglia: Griglia) -> list[CellInsarFeatures]:
    """Una riga per cella. Pura: nessun I/O."""
    v, e = griglia.verticale, griglia.est
    out: list[CellInsarFeatures] = []
    for c in celle:
        # Centro del pixel j a left + (j + 0.5) * passo: dentro la cella se
        # minx <= centro < maxx.
        c0 = max(0, math.ceil((c.minx - griglia.left) / PASSO_M - 0.5))
        c1 = min(v.shape[1], math.ceil((c.maxx - griglia.left) / PASSO_M - 0.5))
        r0 = max(0, math.ceil((griglia.top - c.maxy) / PASSO_M - 0.5))
        r1 = min(v.shape[0], math.ceil((griglia.top - c.miny) / PASSO_M - 0.5))
        vv = v[r0:r1, c0:c1]
        ee = e[r0:r1, c0:c1]
        entrambi = ~np.isnan(vv) & ~np.isnan(ee)
        n = int(entrambi.sum())
        if n == 0:
            out.append(CellInsarFeatures(cell_id=c.cell_id, scatterer_count=0))
            continue
        modulo = np.sqrt(vv[entrambi] ** 2 + ee[entrambi] ** 2)
        out.append(
            CellInsarFeatures(
                cell_id=c.cell_id,
                insar_velocity_mmy=float(np.percentile(modulo, 90)),
                velocita_verticale_mmy=float(np.median(vv[entrambi])),
                velocita_est_mmy=float(np.median(ee[entrambi])),
                scatterer_count=n,
            )
        )
    return out


__all__ = ["Cella", "Griglia", "mosaico", "per_cella"]
