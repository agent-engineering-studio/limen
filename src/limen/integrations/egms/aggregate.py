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
  dire «il satellite qui non vede» (bosco, ombra radar), non «terreno fermo»;
* ``insar_accel_mmy2`` — il 90° percentile del modulo dell'accelerazione, con
  la stessa logica della velocità (#380);
* ``stagionalita_verticale_mm`` — la mediana dell'ampiezza del ciclo annuale
  della componente verticale.

Accelerazione e stagionalità vengono dal CSV della tile, non dal GeoTIFF:
:func:`su_griglia` li riporta sulla griglia del mosaico, pixel per pixel.
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
    #: Dal CSV (:func:`su_griglia`); None se la tile non l'aveva.
    accelerazione_verticale: Any = None
    accelerazione_est: Any = None
    stagionalita_verticale: Any = None


def mosaico(tiff: list[Path], *, minx: float, miny: float, maxx: float, maxy: float) -> Any:
    """Le tile di una componente incollate sul rettangolo, NaN dove mancano.

    Dal pacchetto ``egms-client``: i limiti si allargano ai multipli di 100 m,
    ogni tile si copia al suo posto senza ricampionare, e una tile che dichiara
    ``IGNF:ETRS89LAEA`` (quattro nella release 2020-2025) è EPSG:3035 lo stesso.
    """
    from egms_client.mosaic import mosaic

    return mosaic(tiff, minx=minx, miny=miny, maxx=maxx, maxy=maxy).values


#: Le colonne del CSV L3 che servono, oltre alla posizione del pixel.
COLONNE_ATTRIBUTI = ("acceleration", "seasonality")


def leggi_attributi(csv: Any) -> dict[str, Any]:
    """Posizione, accelerazione e stagionalità di ogni pixel del CSV di una tile.

    Solo quattro colonne su ~300: la serie storica resta nello ZIP.
    """
    import pandas as pd

    tabella = pd.read_csv(csv, usecols=["easting", "northing", *COLONNE_ATTRIBUTI])
    return {c: tabella[c].to_numpy(dtype="float64") for c in tabella.columns}


def su_griglia(
    attributi: list[Path], colonna: str, *, forma: tuple[int, int], left: float, top: float
) -> Any:
    """Una colonna dei CSV (salvati come ``.npz``) sulla griglia del mosaico.

    ``easting``/``northing`` sono il centro del pixel in EPSG:3035, quindi la
    cella della griglia è esatta, senza ricampionare. NaN dove manca.
    """
    out = np.full(forma, np.nan, dtype="float32")
    for path in attributi:
        with np.load(path) as a:
            col = np.floor((a["easting"] - left) / PASSO_M).astype(np.int64)
            riga = np.floor((top - a["northing"]) / PASSO_M).astype(np.int64)
            dentro = (riga >= 0) & (riga < forma[0]) & (col >= 0) & (col < forma[1])
            out[riga[dentro], col[dentro]] = a[colonna][dentro]
    return out


def _p90_modulo(a: Any, b: Any) -> float | None:
    validi = ~np.isnan(a) & ~np.isnan(b)
    if not validi.any():
        return None
    return float(np.percentile(np.sqrt(a[validi] ** 2 + b[validi] ** 2), 90))


def _mediana(a: Any) -> float | None:
    validi = ~np.isnan(a)
    return float(np.median(a[validi])) if validi.any() else None


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
        accelerazione = stagionalita = None
        if griglia.accelerazione_verticale is not None and griglia.accelerazione_est is not None:
            accelerazione = _p90_modulo(
                griglia.accelerazione_verticale[r0:r1, c0:c1],
                griglia.accelerazione_est[r0:r1, c0:c1],
            )
        if griglia.stagionalita_verticale is not None:
            stagionalita = _mediana(griglia.stagionalita_verticale[r0:r1, c0:c1])
        out.append(
            CellInsarFeatures(
                cell_id=c.cell_id,
                insar_velocity_mmy=float(np.percentile(modulo, 90)),
                insar_accel_mmy2=accelerazione,
                velocita_verticale_mmy=float(np.median(vv[entrambi])),
                velocita_est_mmy=float(np.median(ee[entrambi])),
                scatterer_count=n,
                stagionalita_verticale_mm=stagionalita,
            )
        )
    return out


__all__ = [
    "COLONNE_ATTRIBUTI",
    "Cella",
    "Griglia",
    "leggi_attributi",
    "mosaico",
    "per_cella",
    "su_griglia",
]
