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


def _e_laea(crs: Any) -> bool:
    """Vero se ``crs`` è EPSG:3035 nei parametri, qualunque etichetta porti.

    Alcune tile (E42N26, E43N26 nella release 2020-2024) dichiarano
    ``IGNF:ETRS89LAEA``: la stessa proiezione con il nome dell'IGN francese.
    Il confronto per nome le rifiuterebbe; quello per parametri no.
    """
    from pyproj import CRS

    return bool(CRS.from_wkt(crs.to_wkt()).to_proj4() == CRS.from_epsg(3035).to_proj4())


def mosaico(tiff: list[Path], *, minx: float, miny: float, maxx: float, maxy: float) -> Any:
    """Le tile di una componente incollate sul rettangolo, NaN dove mancano.

    I limiti si allargano ai multipli di 100 m: le tile EGMS stanno su quella
    griglia, e ogni tile si copia al suo posto senza ricampionare.
    """
    import warnings

    import rasterio

    x0 = math.floor(minx / PASSO_M) * PASSO_M
    y0 = math.floor(miny / PASSO_M) * PASSO_M
    x1 = math.ceil(maxx / PASSO_M) * PASSO_M
    y1 = math.ceil(maxy / PASSO_M) * PASSO_M
    righe = round((y1 - y0) / PASSO_M)
    colonne = round((x1 - x0) / PASSO_M)
    out = np.full((righe, colonne), np.nan, dtype="float32")
    for path in tiff:
        with rasterio.open(path) as r:
            with warnings.catch_warnings():
                # pyproj avverte che la stringa PROJ perde informazioni: qui
                # servono proprio e solo i parametri.
                warnings.simplefilter("ignore", UserWarning)
                if not _e_laea(r.crs):
                    raise ValueError(f"{path.name}: proiezione non LAEA Europa ({r.crs})")
            banda = r.read(1).astype("float32")
            if r.nodata is not None:
                banda[banda == r.nodata] = np.nan
            # Posizione della tile sulla griglia di uscita, in pixel.
            c = round((r.bounds.left - x0) / PASSO_M)
            rr = round((y1 - r.bounds.top) / PASSO_M)
        sr0, sc0 = max(0, -rr), max(0, -c)
        dr0, dc0 = max(0, rr), max(0, c)
        h = min(banda.shape[0] - sr0, righe - dr0)
        w = min(banda.shape[1] - sc0, colonne - dc0)
        if h <= 0 or w <= 0:
            continue
        pezzo = banda[sr0 : sr0 + h, sc0 : sc0 + w]
        dest = out[dr0 : dr0 + h, dc0 : dc0 + w]
        valido = ~np.isnan(pezzo)
        dest[valido] = pezzo[valido]
    return out


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
