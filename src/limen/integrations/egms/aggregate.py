"""Dalla griglia EGMS a 100 m alle celle da 1 km di Limen.

Le celle sono quadrati da 1 km in EPSG:3035 con un'origine per AOI, quindi
non allineati ai pixel da 100 m delle tile: una cella prende i pixel il cui
**centro** cade dentro di lei, di norma 10 x 10. Le statistiche sono di
``egms_client.cells.per_cell`` (#700), tutte sugli stessi pixel, quelli con
entrambe le componenti della velocità:

* ``velocita_verticale_mmy`` / ``velocita_est_mmy`` — la mediana di ciascuna
  componente, con segno (su/giù, est/ovest);
* ``velocita_verticale_p10_mmy`` — il 10° percentile della verticale: i pixel
  che scendono di più;
* ``insar_velocity_mmy`` — il 90° percentile del modulo ``sqrt(E² + U²)``:
  una frana occupa pochi pixel di una cella da 1 km, e la mediana la
  cancellerebbe;
* ``scatterer_count`` — i pixel validi (da 100 m, non bersagli radar). Zero
  vuol dire «il satellite qui non vede» (bosco, ombra radar), non «terreno
  fermo»; ``copertura`` è la loro parte sui pixel della cella;
* ``accelerazione_verticale_mmy2`` e ``…_p10_mmy2`` — mediana e 10°
  percentile dell'accelerazione verticale, con segno. Il modulo di prima
  (``insar_accel_mmy2``) non si calcola più: era sempre positivo;
* ``stagionalita_verticale_mm`` — la mediana dell'ampiezza del ciclo annuale
  della componente verticale.

Accelerazione e stagionalità vengono dal CSV della tile verticale, non dal
GeoTIFF: :func:`su_griglia` li riporta sulla griglia del mosaico.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from limen.data.repos.cell_insar_features_repo import CellInsarFeatures

if TYPE_CHECKING:
    from egms_client.mosaic import Mosaic


@dataclass(frozen=True, slots=True)
class Cella:
    """Una cella con i suoi limiti in EPSG:3035."""

    cell_id: str
    minx: float
    miny: float
    maxx: float
    maxy: float


def mosaico(tiff: list[Path], *, minx: float, miny: float, maxx: float, maxy: float) -> Mosaic:
    """Le tile di una componente incollate sul rettangolo, NaN dove mancano.

    Dal pacchetto ``egms-client``: i limiti si allargano ai multipli di 100 m,
    ogni tile si copia al suo posto senza ricampionare, e una tile che dichiara
    ``IGNF:ETRS89LAEA`` (quattro nella release 2020-2025) è EPSG:3035 lo stesso.
    """
    from egms_client.mosaic import mosaic

    return mosaic(tiff, minx=minx, miny=miny, maxx=maxx, maxy=maxy)


#: Le colonne del CSV L3 che servono, oltre alla posizione del pixel.
COLONNE_ATTRIBUTI = ("acceleration", "seasonality")


def leggi_attributi(csv: Any) -> dict[str, Any]:
    """Posizione, accelerazione e stagionalità di ogni pixel del CSV di una tile.

    Solo quattro colonne su ~300: la serie storica resta nello ZIP.
    """
    import pandas as pd

    tabella = pd.read_csv(csv, usecols=["easting", "northing", *COLONNE_ATTRIBUTI])
    return {c: tabella[c].to_numpy(dtype="float64") for c in tabella.columns}


def su_griglia(attributi: list[Path], colonna: str, come: Mosaic) -> Any:
    """Una colonna dei CSV (salvati come ``.npz``) sulla griglia di un mosaico.

    ``easting``/``northing`` sono il centro del pixel in EPSG:3035, quindi la
    cella della griglia è esatta, senza ricampionare. NaN dove manca.
    """
    righe, colonne = come.values.shape
    out = np.full((righe, colonne), np.nan, dtype="float32")
    for path in attributi:
        with np.load(path) as a:
            col = np.floor((a["easting"] - come.left) / come.pixel).astype(np.int64)
            riga = np.floor((come.top - a["northing"]) / come.pixel).astype(np.int64)
            dentro = (riga >= 0) & (riga < righe) & (col >= 0) & (col < colonne)
            out[riga[dentro], col[dentro]] = a[colonna][dentro]
    return out


def per_cella(
    celle: list[Cella],
    verticale: Mosaic,
    est: Mosaic,
    *,
    accelerazione: Any = None,
    stagionalita: Any = None,
) -> list[CellInsarFeatures]:
    """Una riga per cella. Pura: nessun I/O.

    ``accelerazione`` e ``stagionalita`` sono le colonne del CSV verticale
    sulla griglia dei mosaici (:func:`su_griglia`); ``None`` se mancano.
    """
    from egms_client.cells import Cell, per_cell

    statistiche = per_cell(
        [Cell(c.cell_id, c.minx, c.miny, c.maxx, c.maxy) for c in celle],
        verticale,
        est,
        acceleration=accelerazione,
        seasonality=stagionalita,
    )
    return [
        CellInsarFeatures(
            cell_id=s.id,
            insar_velocity_mmy=s.speed_p90,
            velocita_verticale_mmy=s.vertical_median,
            velocita_est_mmy=s.east_median,
            scatterer_count=s.valid_pixels,
            stagionalita_verticale_mm=s.seasonality_median,
            accelerazione_verticale_mmy2=s.acceleration_median,
            accelerazione_verticale_p10_mmy2=s.acceleration_p10,
            velocita_verticale_p10_mmy=s.vertical_p10,
            # Senza pixel della griglia nella cella non c'è una copertura da dire.
            copertura=s.coverage if s.pixels else None,
        )
        for s in statistiche
    ]


__all__ = [
    "COLONNE_ATTRIBUTI",
    "Cella",
    "leggi_attributi",
    "mosaico",
    "per_cella",
    "su_griglia",
]
